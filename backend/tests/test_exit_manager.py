"""Tests for hybrid exit evaluation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.engine.exit_manager import calculate_trailing_stop, evaluate_exit


def _position(**overrides):
    base = {
        "entry_price": Decimal("85000"),
        "entry_atr": Decimal("350"),
        "stop_loss_price": Decimal("84300"),
        "take_profit_price": Decimal("86400"),
        "trailing_stop_price": None,
        "opened_at": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_calculate_trailing_stop_activates_after_one_atr_profit():
    trailing = calculate_trailing_stop(
        entry_price=Decimal("85000"),
        current_price=Decimal("86000"),
        entry_atr=Decimal("350"),
        atr_trail_multiplier=Decimal("1.5"),
        current_trailing_stop=None,
    )
    assert trailing == Decimal("85475.00000000")


def test_evaluate_exit_returns_take_profit_before_other_checks():
    decision = evaluate_exit(position=_position(), current_price=Decimal("86450"))
    assert decision.exit_type == "take_profit"
    assert decision.quantity_pct == Decimal("0.7")
    assert decision.updated_trailing_stop_price is not None


def test_evaluate_exit_returns_time_stop_for_stale_trade():
    position = _position(
        take_profit_price=None,
        opened_at=datetime.now(timezone.utc) - timedelta(hours=60),
    )
    decision = evaluate_exit(position=position, current_price=Decimal("85100"))
    assert decision.exit_type == "time_stop"


def test_evaluate_exit_returns_signal_reversal_for_large_negative_score():
    position = _position(take_profit_price=None)
    decision = evaluate_exit(position=position, current_price=Decimal("85200"), composite_score=-0.45)
    assert decision.exit_type == "signal_reversal"
