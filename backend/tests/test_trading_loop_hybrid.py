"""Focused tests for hybrid trading loop helpers."""

from decimal import Decimal
from types import SimpleNamespace

from app.config import Settings
from app.engine.post_trade import update_strategy_streak as _update_strategy_streak
from app.engine import trading_loop as trading_loop_module
from app.engine.trading_loop import (
    _confidence_bucket,
    _hybrid_calibration_multiplier,
    _normalize_ai_counters,
    _regime_entry_policy,
)
from app.regime.types import MarketRegime


def test_confidence_bucket_groups_deciles():
    assert _confidence_bucket(0.04) == "00-09"
    assert _confidence_bucket(0.35) == "30-39"
    assert _confidence_bucket(0.89) == "80-89"


def test_hybrid_calibration_multiplier_uses_bucket_win_rate_after_minimum_sample():
    config = {
        "hybrid_confidence_calibration": {
            "80-89": {"trades": 25, "wins": 20, "avg_pnl_pct": 3.2}
        }
    }
    assert _hybrid_calibration_multiplier(config, "80-89") == 1.15


def test_regime_entry_policy_blocks_downtrend_and_scales_high_volatility():
    allowed, size_multiplier, min_confidence, reason = _regime_entry_policy(
        "sma_crossover", MarketRegime.TRENDING_DOWN, 0.30
    )
    assert allowed is False
    assert "blocks new long entries" in reason

    allowed, size_multiplier, min_confidence, reason = _regime_entry_policy(
        "macd_momentum", MarketRegime.HIGH_VOLATILITY, 0.30
    )
    assert allowed is True
    assert size_multiplier == Decimal("0.5")
    assert min_confidence == 0.40


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


def test_normalize_ai_counters_prefers_strategy_provider_and_env_model(monkeypatch):
    monkeypatch.setattr(
        trading_loop_module,
        "settings",
        Settings(ai_provider="openai", ai_model="gpt-4.1-mini", openai_model="gpt-5.4-mini"),
    )

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
    assert result["ai_model"] == "gpt-4.1-mini"
    assert result["ai_strategy_key"] == "hybrid_composite"
