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
