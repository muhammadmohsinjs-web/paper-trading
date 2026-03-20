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


def test_hard_stop_triggers_at_stop_loss_price():
    position = _position(stop_loss_price=Decimal("84300"))
    decision = evaluate_exit(position=position, current_price=Decimal("84300"))
    assert decision.exit_type == "stop_loss"
    assert decision.quantity_pct == Decimal("1.0")


def test_hard_stop_does_not_trigger_above_stop():
    position = _position(stop_loss_price=Decimal("84300"))
    decision = evaluate_exit(position=position, current_price=Decimal("84300.01"))
    assert decision.action == "HOLD"


def test_trailing_stop_ratchets_up_only():
    trailing1 = calculate_trailing_stop(
        entry_price=Decimal("85000"),
        current_price=Decimal("86000"),
        entry_atr=Decimal("350"),
        atr_trail_multiplier=Decimal("1.5"),
        current_trailing_stop=None,
    )
    assert trailing1 is not None

    # Price drops — trailing should NOT decrease
    trailing2 = calculate_trailing_stop(
        entry_price=Decimal("85000"),
        current_price=Decimal("85500"),
        entry_atr=Decimal("350"),
        atr_trail_multiplier=Decimal("1.5"),
        current_trailing_stop=trailing1,
    )
    assert trailing2 == trailing1


def test_trailing_stop_multiple_ratchets():
    entry = Decimal("85000")
    atr = Decimal("350")
    mult = Decimal("1.5")

    t1 = calculate_trailing_stop(
        entry_price=entry, current_price=Decimal("85300"),
        entry_atr=atr, atr_trail_multiplier=mult, current_trailing_stop=None,
    )
    assert t1 is None  # < 1 ATR above entry

    t2 = calculate_trailing_stop(
        entry_price=entry, current_price=Decimal("86000"),
        entry_atr=atr, atr_trail_multiplier=mult, current_trailing_stop=t1,
    )
    assert t2 is not None

    t3 = calculate_trailing_stop(
        entry_price=entry, current_price=Decimal("87000"),
        entry_atr=atr, atr_trail_multiplier=mult, current_trailing_stop=t2,
    )
    assert t3 > t2


def test_take_profit_partial_70pct():
    decision = evaluate_exit(position=_position(), current_price=Decimal("86450"))
    assert decision.quantity_pct == Decimal("0.7")
    assert decision.consume_take_profit is True


def test_stop_loss_priority_over_take_profit():
    position = _position(
        stop_loss_price=Decimal("84300"),
        take_profit_price=Decimal("84000"),
    )
    decision = evaluate_exit(position=position, current_price=Decimal("84000"))
    assert decision.exit_type == "stop_loss"


def test_hold_when_no_exit_conditions():
    position = _position(take_profit_price=None, stop_loss_price=None)
    decision = evaluate_exit(position=position, current_price=Decimal("85100"))
    assert decision.action == "HOLD"
    assert decision.quantity_pct == Decimal("0")


def test_signal_reversal_at_threshold_boundary():
    position = _position(take_profit_price=None)
    decision = evaluate_exit(position=position, current_price=Decimal("85200"), composite_score=-0.4)
    assert decision.exit_type == "signal_reversal"


def test_signal_reversal_not_triggered_above_threshold():
    position = _position(take_profit_price=None)
    decision = evaluate_exit(position=position, current_price=Decimal("85200"), composite_score=-0.3)
    assert decision.action == "HOLD"


def test_trailing_stop_trigger():
    decision = evaluate_exit(
        position=_position(
            entry_price=Decimal("84000"),
            entry_atr=Decimal("350"),
            stop_loss_price=None,
            take_profit_price=None,
            trailing_stop_price=Decimal("85500"),
        ),
        current_price=Decimal("85400"),
    )
    assert decision.exit_type == "trailing_stop"
