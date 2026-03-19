"""Tests for the hybrid composite scorer."""

from app.engine.composite_scorer import (
    compute_ai_vote,
    compute_composite_score,
    ema_vote,
    macd_vote,
    rsi_vote,
    sma_vote,
    volume_vote,
)


def test_rsi_vote_extremes():
    assert rsi_vote(15.0) == 1.0
    assert rsi_vote(75.0) == -0.8
    assert rsi_vote(50.0) == 0.0


def test_macd_vote_detects_bullish_crossover():
    assert macd_vote([0.1, 0.5], [0.2, 0.4], [-0.1, 0.1]) == 0.8


def test_sma_vote_detects_bearish_widening_gap():
    assert sma_vote([99.0, 98.0], [100.0, 101.5]) == -0.5


def test_ema_vote_detects_bullish_acceleration():
    assert ema_vote([100.0, 103.0], [99.0, 101.0]) == 0.5


def test_volume_vote_applies_dampening_on_dry_volume():
    vote, dampening = volume_vote(0.4, 101.0, 100.0)
    assert vote == 0.0
    assert dampening == 0.5


def test_compute_ai_vote_returns_none_without_complete_inputs():
    assert compute_ai_vote(None, 0.8, 1.0) is None
    assert compute_ai_vote(0.7, None, 1.0) is None


def test_compute_composite_score_uses_ai_fallback_weights_when_ai_missing():
    indicators = {
        "rsi": [25.0],
        "macd": ([0.4, 0.5], [0.45, 0.4], [-0.05, 0.1]),
        "sma_short": [100.0, 102.0],
        "sma_long": [101.0, 101.5],
        "ema_12": [100.0, 103.0],
        "ema_26": [99.0, 101.0],
        "volume_ratio": [1.6],
        "latest_close": 105.0,
        "previous_close": 104.0,
    }

    result = compute_composite_score(indicators)

    assert result.ai_vote_present is False
    assert "ai" not in result.weights
    assert abs(sum(result.weights.values()) - 1.0) < 1e-9
    assert result.signal == "BUY"
    assert result.composite_score > 0


def test_compute_composite_score_respects_configured_ai_disabled_weights():
    indicators = {
        "rsi": [75.0],
        "macd": ([-0.4, -0.5], [-0.3, -0.4], [-0.1, -0.1]),
        "sma_short": [100.0, 99.0],
        "sma_long": [100.5, 100.8],
        "ema_12": [100.0, 98.0],
        "ema_26": [99.5, 99.0],
        "volume_ratio": [1.6],
        "latest_close": 99.0,
        "previous_close": 100.0,
    }
    config = {
        "weight_rsi": 0.27,
        "weight_macd": 0.27,
        "weight_sma": 0.20,
        "weight_ema": 0.13,
        "weight_volume": 0.13,
        "weight_ai": 0.0,
        "confidence_gate": 0.5,
    }

    result = compute_composite_score(indicators, config=config)

    assert result.weights["rsi"] == 0.27
    assert result.weights["macd"] == 0.27
    assert result.signal == "SELL"
