"""Composite signal scoring for the hybrid trading strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_WEIGHTS = {
    "rsi": 0.20,
    "macd": 0.25,
    "sma": 0.15,
    "ema": 0.10,
    "volume": 0.15,
    "ai": 0.15,
}

DEFAULT_CONFIDENCE_GATE = 0.5
DEFAULT_VOLUME_DAMPENING_MULTIPLIER = 0.5


@dataclass(frozen=True)
class CompositeScoreResult:
    votes: dict[str, float]
    weights: dict[str, float]
    composite_score: float
    confidence: float
    direction: str
    signal: str
    dampening_multiplier: float
    ai_vote_present: bool


def rsi_vote(value: float | None) -> float:
    if value is None:
        return 0.0
    if value < 20:
        return 1.0
    if value < 30:
        return 0.8
    if value < 40:
        return 0.3
    if value > 80:
        return -1.0
    if value > 70:
        return -0.8
    if value > 60:
        return -0.3
    return 0.0


def macd_vote(macd_line: list[float], signal_line: list[float], histogram: list[float]) -> float:
    if len(macd_line) < 2 or len(signal_line) < 2 or len(histogram) < 2:
        return 0.0

    prev_macd, curr_macd = macd_line[-2], macd_line[-1]
    prev_signal, curr_signal = signal_line[-2], signal_line[-1]
    prev_hist, curr_hist = histogram[-2], histogram[-1]

    if prev_macd <= prev_signal and curr_macd > curr_signal:
        return 0.8
    if prev_macd >= prev_signal and curr_macd < curr_signal:
        return -0.8
    if curr_macd > curr_signal:
        return 0.5 if curr_hist > prev_hist else 0.2
    if curr_macd < curr_signal:
        return -0.2 if abs(curr_hist) < abs(prev_hist) else -0.5
    return 0.0


def sma_vote(short_sma: list[float], long_sma: list[float]) -> float:
    if len(short_sma) < 2 or len(long_sma) < 2:
        return 0.0

    prev_gap = short_sma[-2] - long_sma[-2]
    curr_gap = short_sma[-1] - long_sma[-1]

    if prev_gap <= 0 < curr_gap:
        return 0.8
    if prev_gap >= 0 > curr_gap:
        return -0.8
    if curr_gap > 0:
        return 0.5 if abs(curr_gap) > abs(prev_gap) else 0.2
    if curr_gap < 0:
        return -0.2 if abs(curr_gap) < abs(prev_gap) else -0.5
    return 0.0


def ema_vote(fast_ema: list[float], slow_ema: list[float]) -> float:
    if len(fast_ema) < 2 or len(slow_ema) < 2:
        return 0.0

    prev_gap = fast_ema[-2] - slow_ema[-2]
    curr_gap = fast_ema[-1] - slow_ema[-1]

    if curr_gap > 0:
        return 0.5 if abs(curr_gap) > abs(prev_gap) else 0.2
    if curr_gap < 0:
        return -0.2 if abs(curr_gap) < abs(prev_gap) else -0.5
    return 0.0


def volume_vote(
    volume_ratio: float | None,
    latest_close: float | None,
    previous_close: float | None,
) -> tuple[float, float]:
    if volume_ratio is None:
        return 0.0, 1.0

    if volume_ratio < 0.5:
        return 0.0, DEFAULT_VOLUME_DAMPENING_MULTIPLIER

    if latest_close is None or previous_close is None:
        if volume_ratio < 0.7:
            return 0.0, 1.0
        return 0.0, 1.0

    price_up = latest_close > previous_close
    price_down = latest_close < previous_close

    if volume_ratio > 1.5 and price_up:
        return 0.8, 1.0
    if volume_ratio > 1.5 and price_down:
        return -0.8, 1.0
    if volume_ratio > 1.0 and price_up:
        return 0.3, 1.0
    if volume_ratio > 1.0 and price_down:
        return -0.3, 1.0
    if volume_ratio < 0.7:
        return 0.0, 1.0
    return 0.0, 1.0


def compute_ai_vote(
    bias: float | None,
    confidence: float | None,
    freshness_decay: float | None,
) -> float | None:
    if bias is None or confidence is None:
        return None
    decay = 1.0 if freshness_decay is None else freshness_decay
    return float(bias) * float(confidence) * float(decay)


def _configured_weights(config: dict[str, Any] | None) -> dict[str, float]:
    cfg = config or {}
    weights = DEFAULT_WEIGHTS.copy()
    for key in weights:
        cfg_key = f"weight_{key}"
        if cfg_key in cfg:
            weights[key] = float(cfg[cfg_key])
    return weights


def _resolve_weights(config: dict[str, Any] | None, ai_vote: float | None) -> dict[str, float]:
    weights = _configured_weights(config)
    if ai_vote is not None:
        return weights

    non_ai_weights = {key: value for key, value in weights.items() if key != "ai"}
    total = sum(non_ai_weights.values())
    if total <= 0:
        return {**DEFAULT_WEIGHTS, "ai": 0.0}
    return {key: value / total for key, value in non_ai_weights.items()}


def compute_composite_score(
    indicators: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    ai_vote_value: float | None = None,
) -> CompositeScoreResult:
    latest_rsi = indicators.get("rsi", [None])[-1] if indicators.get("rsi") else None
    macd_line, signal_line, histogram = indicators.get("macd", ([], [], []))
    latest_volume_ratio = indicators.get("volume_ratio", [None])[-1] if indicators.get("volume_ratio") else None

    votes = {
        "rsi": rsi_vote(latest_rsi),
        "macd": macd_vote(macd_line, signal_line, histogram),
        "sma": sma_vote(indicators.get("sma_short", []), indicators.get("sma_long", [])),
        "ema": ema_vote(indicators.get("ema_12", []), indicators.get("ema_26", [])),
    }
    volume_vote_value, dampening_multiplier = volume_vote(
        latest_volume_ratio,
        indicators.get("latest_close"),
        indicators.get("previous_close"),
    )
    votes["volume"] = volume_vote_value

    ai_vote_present = ai_vote_value is not None
    if ai_vote_present:
        votes["ai"] = float(ai_vote_value)

    weights = _resolve_weights(config, ai_vote_value)
    weighted_sum = sum(votes[key] * weights.get(key, 0.0) for key in votes)
    composite_score = max(min(weighted_sum * dampening_multiplier, 1.0), -1.0)
    confidence = abs(composite_score)

    if composite_score > 0:
        direction = "BUY"
    elif composite_score < 0:
        direction = "SELL"
    else:
        direction = "HOLD"

    gate = float((config or {}).get("confidence_gate", DEFAULT_CONFIDENCE_GATE))
    signal = direction if direction != "HOLD" and confidence >= gate else "HOLD"

    return CompositeScoreResult(
        votes=votes,
        weights=weights,
        composite_score=composite_score,
        confidence=confidence,
        direction=direction,
        signal=signal,
        dampening_multiplier=dampening_multiplier,
        ai_vote_present=ai_vote_present,
    )
