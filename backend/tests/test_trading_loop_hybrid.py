"""Focused tests for hybrid trading loop helpers."""

from decimal import Decimal
from types import SimpleNamespace

from app.engine.ai_runtime import AIDecisionResult
from app.engine.trading_loop import (
    _hybrid_ai_vote_value,
    _normalize_ai_counters,
    _update_strategy_streak,
)


def test_hybrid_ai_vote_uses_action_and_confidence():
    buy_vote = _hybrid_ai_vote_value(
        AIDecisionResult(status="signal", action="BUY", confidence=0.8)
    )
    sell_vote = _hybrid_ai_vote_value(
        AIDecisionResult(status="signal", action="SELL", confidence=0.35)
    )
    hold_vote = _hybrid_ai_vote_value(
        AIDecisionResult(status="hold", action="HOLD", confidence=0.9)
    )

    assert buy_vote == 0.8
    assert sell_vote == -0.35
    assert hold_vote == 0.0


def test_update_strategy_streak_increments_on_losses_and_resets_on_profit():
    strategy = SimpleNamespace(
        consecutive_losses=2,
        max_consecutive_losses=2,
        streak_size_multiplier=Decimal("1.0"),
    )

    _update_strategy_streak(strategy, Decimal("-5"))
    assert strategy.consecutive_losses == 3
    assert strategy.max_consecutive_losses == 3
    assert strategy.streak_size_multiplier == Decimal("0.50")

    _update_strategy_streak(strategy, Decimal("3"))
    assert strategy.consecutive_losses == 0
    assert strategy.max_consecutive_losses == 3
    assert strategy.streak_size_multiplier == Decimal("1.0")


def test_normalize_ai_counters_prefers_strategy_provider_and_model():
    strategy = SimpleNamespace(
        config_json={"strategy_type": "hybrid_composite", "ai_enabled": True},
        ai_enabled=True,
        ai_provider="openai",
        ai_strategy_key=None,
        ai_model="gpt-5-mini",
        ai_cooldown_seconds=60,
        ai_max_tokens=700,
        ai_temperature=Decimal("0.2"),
    )

    result = _normalize_ai_counters(strategy)

    assert result["ai_provider"] == "openai"
    assert result["ai_model"] == "gpt-5-mini"
    assert result["ai_strategy_key"] == "hybrid_composite"
