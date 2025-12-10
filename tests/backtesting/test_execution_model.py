"""Unit tests for execution realism models (Phase 2A)."""

import pytest
from datetime import datetime, date, time, timedelta

from alpaca_options.backtesting.execution_model import (
    FillProbabilityModel,
    FillContext,
    GapRiskModel,
)


# ============================================================================
# Fill Probability Model Tests
# ============================================================================


def test_fill_probability_liquid_option():
    """Liquid option should have high fill probability."""
    model = FillProbabilityModel()

    context = FillContext(
        open_interest=5000,
        bid_ask_spread_pct=0.02,  # 2% spread
        timestamp=datetime(2024, 6, 15, 11, 0),  # Mid-day
        vix=18.0,  # Low volatility
        order_size=1,
        avg_daily_volume=10000,
        option_type="put",
        is_opening=True,
    )

    prob = model.calculate_fill_probability(context)
    assert prob >= 0.95, f"Expected >= 95% but got {prob:.1%}"


def test_fill_probability_illiquid_option_rejects():
    """Illiquid option should have zero fill probability."""
    model = FillProbabilityModel()

    context = FillContext(
        open_interest=30,  # Below min threshold (50)
        bid_ask_spread_pct=0.15,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=50,
        option_type="put",
        is_opening=True,
    )

    prob = model.calculate_fill_probability(context)
    assert prob == 0.0, f"Expected 0% but got {prob:.1%}"


def test_fill_probability_wide_spread_rejects():
    """Wide spread (>10%) should reject."""
    model = FillProbabilityModel()

    context = FillContext(
        open_interest=1000,  # Good OI
        bid_ask_spread_pct=0.12,  # 12% spread (too wide)
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    prob = model.calculate_fill_probability(context)
    assert prob == 0.0, f"Expected rejection but got {prob:.1%}"


def test_fill_probability_low_oi():
    """Low OI (50-200) should have ~50% fill rate."""
    model = FillProbabilityModel()

    context = FillContext(
        open_interest=150,  # Low but above minimum
        bid_ask_spread_pct=0.04,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=1000,
        option_type="put",
        is_opening=True,
    )

    prob = model.calculate_fill_probability(context)
    # Should be ~50% (base 0.5 from OI)
    assert 0.45 <= prob <= 0.55, f"Expected ~50% but got {prob:.1%}"


def test_fill_probability_moderate_oi():
    """Moderate OI (500-1000) should have ~90% fill rate."""
    model = FillProbabilityModel()

    context = FillContext(
        open_interest=750,  # Moderate OI
        bid_ask_spread_pct=0.03,  # Tight spread
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    prob = model.calculate_fill_probability(context)
    # Should be ~90% (base 0.9 from OI, 0.95 from spread)
    assert 0.85 <= prob <= 0.95, f"Expected ~90% but got {prob:.1%}"


def test_fill_probability_market_close_penalty():
    """Fill probability should be lower near market close."""
    model = FillProbabilityModel()

    base_context = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 11, 0),  # Mid-day
        vix=20.0,
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    close_context = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 15, 45),  # Near close (3:45pm)
        vix=20.0,
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    prob_midday = model.calculate_fill_probability(base_context)
    prob_close = model.calculate_fill_probability(close_context)

    assert prob_close < prob_midday, "Close should have lower probability"
    # Should be ~15% penalty (0.85 multiplier)
    assert prob_close / prob_midday == pytest.approx(0.85, rel=0.01)


def test_fill_probability_market_open_penalty():
    """Fill probability should be lower at market open."""
    model = FillProbabilityModel()

    midday_context = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    open_context = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 9, 45),  # Just after open
        vix=20.0,
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    prob_midday = model.calculate_fill_probability(midday_context)
    prob_open = model.calculate_fill_probability(open_context)

    assert prob_open < prob_midday, "Open should have lower probability"


def test_fill_probability_high_vix():
    """High VIX should reduce fill probability."""
    model = FillProbabilityModel()

    low_vix_context = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=15.0,  # Low VIX
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    high_vix_context = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=35.0,  # High VIX
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    prob_low_vix = model.calculate_fill_probability(low_vix_context)
    prob_high_vix = model.calculate_fill_probability(high_vix_context)

    assert prob_high_vix < prob_low_vix
    # Should be ~10% penalty (0.90 multiplier) for VIX > 30
    assert prob_high_vix / prob_low_vix == pytest.approx(0.90, rel=0.01)


def test_fill_probability_very_high_vix():
    """Very high VIX (>40) should have larger penalty."""
    model = FillProbabilityModel()

    normal_vix = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    extreme_vix = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=45.0,  # Extreme VIX
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    prob_normal = model.calculate_fill_probability(normal_vix)
    prob_extreme = model.calculate_fill_probability(extreme_vix)

    assert prob_extreme < prob_normal
    # Should be ~20% penalty (0.80 multiplier) for VIX > 40
    assert prob_extreme / prob_normal == pytest.approx(0.80, rel=0.01)


def test_fill_probability_large_order():
    """Large order relative to volume should have lower fill probability."""
    model = FillProbabilityModel()

    small_order = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=5,  # 5 contracts
        avg_daily_volume=10000,  # 0.05% of volume
        option_type="put",
        is_opening=True,
    )

    large_order = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=2500,  # 2500 contracts
        avg_daily_volume=10000,  # 25% of volume!
        option_type="put",
        is_opening=True,
    )

    prob_small = model.calculate_fill_probability(small_order)
    prob_large = model.calculate_fill_probability(large_order)

    assert prob_large < prob_small
    # Large order (>20% volume) should have ~50% fill rate


def test_fill_probability_closing_orders_easier():
    """Closing orders should be easier to fill than opening."""
    model = FillProbabilityModel()

    opening_context = FillContext(
        open_interest=500,
        bid_ask_spread_pct=0.04,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=2000,
        option_type="put",
        is_opening=True,
    )

    closing_context = FillContext(
        open_interest=500,
        bid_ask_spread_pct=0.04,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=2000,
        option_type="put",
        is_opening=False,  # Closing order
    )

    prob_opening = model.calculate_fill_probability(opening_context)
    prob_closing = model.calculate_fill_probability(closing_context)

    assert prob_closing >= prob_opening
    # Should be ~10% bonus (1.10 multiplier) for closing


def test_will_fill_deterministic():
    """will_fill should be deterministic with random_seed."""
    model = FillProbabilityModel()

    context = FillContext(
        open_interest=500,
        bid_ask_spread_pct=0.04,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=2000,
        option_type="put",
        is_opening=True,
    )

    # With same seed, should get same result
    result1 = model.will_fill(context, random_seed=0.5)
    result2 = model.will_fill(context, random_seed=0.5)
    assert result1 == result2

    # With different seeds, might get different results
    # (depends on probability)
    result_low = model.will_fill(context, random_seed=0.01)  # Very low random
    result_high = model.will_fill(context, random_seed=0.99)  # Very high random

    # Low random number should fill if prob > 1%
    # High random number should not fill if prob < 99%


def test_will_fill_zero_probability():
    """Zero probability should never fill."""
    model = FillProbabilityModel()

    context = FillContext(
        open_interest=30,  # Below threshold
        bid_ask_spread_pct=0.04,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=100,
        option_type="put",
        is_opening=True,
    )

    # Should never fill, regardless of random seed
    assert not model.will_fill(context, random_seed=0.0)
    assert not model.will_fill(context, random_seed=0.5)
    assert not model.will_fill(context, random_seed=0.99)


# ============================================================================
# Gap Risk Model Tests
# ============================================================================


def test_market_hours_detection_open():
    """Test market open detection."""
    model = GapRiskModel()

    # Monday 11am - should be open
    assert model.is_market_open(datetime(2024, 6, 17, 11, 0))

    # Tuesday 2pm - should be open
    assert model.is_market_open(datetime(2024, 6, 18, 14, 0))


def test_market_hours_detection_closed_before_open():
    """Market should be closed before 9:30am."""
    model = GapRiskModel()

    # Monday 8am - before open
    assert not model.is_market_open(datetime(2024, 6, 17, 8, 0))


def test_market_hours_detection_closed_after_close():
    """Market should be closed after 4pm."""
    model = GapRiskModel()

    # Monday 5pm - after close
    assert not model.is_market_open(datetime(2024, 6, 17, 17, 0))


def test_market_hours_detection_weekend():
    """Market should be closed on weekends."""
    model = GapRiskModel()

    # Saturday 11am
    assert not model.is_market_open(datetime(2024, 6, 15, 11, 0))

    # Sunday 2pm
    assert not model.is_market_open(datetime(2024, 6, 16, 14, 0))


def test_hours_until_open_overnight():
    """Test overnight hours calculation."""
    model = GapRiskModel()

    # 5pm Monday -> 9:30am Tuesday = 16.5 hours
    monday_close = datetime(2024, 6, 17, 17, 0)
    hours = model.hours_until_market_open(monday_close)

    assert 16.0 <= hours <= 17.0, f"Expected ~16.5 hours, got {hours}"


def test_hours_until_open_weekend():
    """Test weekend hours calculation."""
    model = GapRiskModel()

    # 5pm Friday -> 9:30am Monday = ~64.5 hours
    friday_close = datetime(2024, 6, 14, 17, 0)
    hours = model.hours_until_market_open(friday_close)

    assert 64.0 <= hours <= 65.0, f"Expected ~64.5 hours, got {hours}"


def test_hours_until_open_saturday():
    """Saturday should calculate hours to Monday open."""
    model = GapRiskModel()

    # Saturday 11am -> Monday 9:30am
    saturday = datetime(2024, 6, 15, 11, 0)
    hours = model.hours_until_market_open(saturday)

    # ~46.5 hours (11am Sat -> 9:30am Mon)
    assert 46.0 <= hours <= 47.0


def test_hours_until_open_during_market():
    """Should return 0 during market hours."""
    model = GapRiskModel()

    # Tuesday 11am - market is open
    tuesday_open = datetime(2024, 6, 18, 11, 0)
    hours = model.hours_until_market_open(tuesday_open)

    assert hours == 0.0


def test_gap_impact_healthy_position():
    """Healthy position should have no gap impact."""
    model = GapRiskModel()

    # Position with small loss, not near stop
    gap_slippage = model.estimate_gap_impact(
        position_pnl_pct=-0.30,  # Down 30%
        position_notional=1000.0,
        timestamp=datetime(2024, 6, 17, 17, 0),  # After close
        underlying_volatility=0.20,
    )

    assert gap_slippage == 0.0


def test_gap_impact_stop_loss_triggered():
    """Position past stop loss should incur gap slippage."""
    model = GapRiskModel(stop_loss_slippage_pct=0.02)

    # Position lost > 100% (2x credit = stop loss)
    gap_slippage = model.estimate_gap_impact(
        position_pnl_pct=-1.5,  # Down 150% (past stop)
        position_notional=1000.0,
        timestamp=datetime(2024, 6, 17, 17, 0),  # After close
        underlying_volatility=0.20,
    )

    # Should add 2% gap slippage
    expected = 1000.0 * 0.02
    assert gap_slippage == expected


def test_gap_impact_market_open():
    """No gap impact during market hours."""
    model = GapRiskModel()

    gap_slippage = model.estimate_gap_impact(
        position_pnl_pct=-1.5,  # Past stop loss
        position_notional=1000.0,
        timestamp=datetime(2024, 6, 17, 11, 0),  # Market open
        underlying_volatility=0.20,
    )

    assert gap_slippage == 0.0


def test_should_check_gap_risk_open_to_close():
    """Should detect crossing from open to close."""
    model = GapRiskModel()

    # 3:30pm (open) -> 5pm (closed)
    current = datetime(2024, 6, 17, 15, 30)
    next_bar = datetime(2024, 6, 17, 17, 0)

    assert model.should_check_gap_risk(current, next_bar)


def test_should_check_gap_risk_close_to_open():
    """Should detect crossing from close to open (gap!)."""
    model = GapRiskModel()

    # 5pm Monday (closed) -> 10am Tuesday (open)
    current = datetime(2024, 6, 17, 17, 0)
    next_bar = datetime(2024, 6, 18, 10, 0)

    assert model.should_check_gap_risk(current, next_bar)


def test_should_check_gap_risk_within_market_hours():
    """Should not trigger during continuous market hours."""
    model = GapRiskModel()

    # 11am -> 12pm (both market hours)
    current = datetime(2024, 6, 17, 11, 0)
    next_bar = datetime(2024, 6, 17, 12, 0)

    assert not model.should_check_gap_risk(current, next_bar)


def test_should_check_gap_risk_within_close_hours():
    """Should not trigger if both times are during close."""
    model = GapRiskModel()

    # 8pm Monday -> 9pm Monday (both closed)
    current = datetime(2024, 6, 17, 20, 0)
    next_bar = datetime(2024, 6, 17, 21, 0)

    assert not model.should_check_gap_risk(current, next_bar)
