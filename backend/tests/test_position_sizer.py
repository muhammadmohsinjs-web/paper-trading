"""Tests for ATR-based position sizing."""

from decimal import Decimal

from app.engine.position_sizer import calculate_position_size, streak_multiplier_for_losses


def test_streak_multiplier_matches_protocol():
    assert streak_multiplier_for_losses(0) == Decimal("1.0")
    assert streak_multiplier_for_losses(3) == Decimal("0.50")
    assert streak_multiplier_for_losses(5) == Decimal("0.25")


def test_position_sizer_caps_by_max_position_pct():
    result = calculate_position_size(
        equity=Decimal("1000"),
        entry_price=Decimal("85000"),
        atr=Decimal("350"),
        confidence_tier="full",
        max_position_pct=Decimal("30"),
    )

    assert result.quantity_pct == Decimal("0.30000000")
    assert result.stop_loss_price == Decimal("84300.00000000")
    assert result.take_profit_price == Decimal("86400.00000000")


def test_position_sizer_reduces_risk_for_small_confidence_and_streak():
    result = calculate_position_size(
        equity=Decimal("1000"),
        entry_price=Decimal("85000"),
        atr=Decimal("1500"),
        confidence_tier="small",
        losing_streak_count=5,
        max_position_pct=Decimal("30"),
    )

    assert result.confidence_multiplier == Decimal("0.4")
    assert result.streak_multiplier == Decimal("0.25")
    assert result.quantity_pct < Decimal("0.10")


def test_atr_formula_stop_distance():
    result = calculate_position_size(
        equity=Decimal("10000"),
        entry_price=Decimal("85000"),
        atr=Decimal("350"),
        atr_multiplier=Decimal("2.0"),
    )
    assert result.stop_distance == Decimal("700.00000000")
    assert result.stop_loss_price == Decimal("84300.00000000")


def test_atr_formula_take_profit():
    result = calculate_position_size(
        equity=Decimal("10000"),
        entry_price=Decimal("85000"),
        atr=Decimal("350"),
        atr_multiplier=Decimal("2.0"),
        take_profit_ratio=Decimal("2.0"),
    )
    assert result.take_profit_price == Decimal("86400.00000000")


def test_zero_atr_returns_zero_position():
    result = calculate_position_size(
        equity=Decimal("10000"),
        entry_price=Decimal("85000"),
        atr=Decimal("0"),
    )
    assert result.quantity_pct == Decimal("0")
    assert result.stop_loss_price == Decimal("85000")


def test_zero_equity_returns_zero_position():
    result = calculate_position_size(
        equity=Decimal("0"),
        entry_price=Decimal("85000"),
        atr=Decimal("350"),
    )
    assert result.quantity_pct == Decimal("0")


def test_very_high_atr_small_position():
    result = calculate_position_size(
        equity=Decimal("1000"),
        entry_price=Decimal("85000"),
        atr=Decimal("5000"),
        confidence_tier="reduced",
    )
    assert result.quantity_pct < Decimal("0.15")


def test_very_low_atr_capped_at_max():
    result = calculate_position_size(
        equity=Decimal("10000"),
        entry_price=Decimal("85000"),
        atr=Decimal("1"),
        confidence_tier="reduced",
        max_position_pct=Decimal("30"),
    )
    assert result.quantity_pct <= Decimal("0.30")


def test_risk_amount_2pct_of_equity():
    result = calculate_position_size(
        equity=Decimal("10000"),
        entry_price=Decimal("85000"),
        atr=Decimal("350"),
        risk_per_trade_pct=Decimal("2.0"),
        confidence_tier="full",
        losing_streak_count=0,
    )
    assert result.risk_amount == Decimal("200.00000000")


def test_full_confidence_caps_at_60pct():
    result = calculate_position_size(
        equity=Decimal("10000"),
        entry_price=Decimal("85000"),
        atr=Decimal("1"),
        confidence_tier="full",
    )
    assert result.quantity_pct <= Decimal("0.60")


def test_streak_multiplier_boundary_2():
    assert streak_multiplier_for_losses(2) == Decimal("1.0")


def test_streak_multiplier_boundary_4():
    assert streak_multiplier_for_losses(4) == Decimal("0.50")
