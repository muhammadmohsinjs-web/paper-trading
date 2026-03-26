"""Composite signal scoring for the hybrid trading strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_WEIGHTS = {
    "rsi": 0.20,
    "macd": 0.20,
    "sma": 0.10,
    "ema": 0.10,
    "volume": 0.25,
    "structure": 0.15,
}

DEFAULT_CONFIDENCE_GATE = 0.35
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


def rsi_vote(value: float | None, divergence: Any | None = None) -> float:
    base = 0.0
    if value is not None:
        if value < 20:
            base = 1.0
        elif value < 30:
            base = 0.8
        elif value < 40:
            base = 0.3
        elif value > 80:
            base = -1.0
        elif value > 70:
            base = -0.8
        elif value > 60:
            base = -0.3

    # Divergence overrides: strongest directional signal
    if divergence is not None and getattr(divergence, "detected", False):
        if divergence.divergence_type == "bullish":
            base = max(base, 0.9)
        elif divergence.divergence_type == "bearish":
            base = min(base, -0.9)

    return base


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


def structure_vote(
    sr_levels: list | None,
    latest_close: float | None,
) -> float:
    """Vote based on proximity to support/resistance levels.

    Bullish if price is near strong support, bearish if near strong resistance.
    """
    if not sr_levels or latest_close is None:
        return 0.0

    from app.market.structure import nearest_resistance, nearest_support

    nearest_sup = nearest_support(sr_levels, latest_close)
    nearest_res = nearest_resistance(sr_levels, latest_close)

    vote = 0.0

    if nearest_sup is not None:
        distance_pct = (latest_close - nearest_sup.price) / latest_close * 100
        if distance_pct < 1.0:  # Within 1% of support
            strength_bonus = min(nearest_sup.strength / 5.0, 1.0)
            vote += 0.5 * strength_bonus

    if nearest_res is not None:
        distance_pct = (nearest_res.price - latest_close) / latest_close * 100
        if distance_pct < 1.0:  # Within 1% of resistance
            strength_bonus = min(nearest_res.strength / 5.0, 1.0)
            vote -= 0.5 * strength_bonus

    return max(-1.0, min(1.0, vote))


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


def _resolve_weights(config: dict[str, Any] | None) -> dict[str, float]:
    weights = _configured_weights(config)
    total = sum(weights.values())
    if total <= 0:
        return DEFAULT_WEIGHTS.copy()
    normalized = {key: value / total for key, value in weights.items()}

    # Adaptive optimization from trade history (if available)
    trade_history = (config or {}).get("recent_trade_history")
    if trade_history and isinstance(trade_history, list):
        from app.engine.weight_optimizer import compute_adaptive_weights
        learning_rate = float((config or {}).get("weight_learning_rate", 0.3))
        normalized = compute_adaptive_weights(trade_history, normalized, learning_rate)

    return normalized


def _volume_quality(volume_ratio: float | None) -> float:
    if volume_ratio is None:
        return 0.3
    if volume_ratio >= 1.5:
        return 1.0
    if volume_ratio >= 1.0:
        return 0.7
    if volume_ratio >= 0.7:
        return 0.4
    if volume_ratio >= 0.5:
        return 0.2
    return 0.0


def _regime_alignment_bonus(regime: str | None, direction: str) -> float:
    if direction != "BUY":
        return 0.0

    normalized = (regime or "").strip().lower()
    if normalized in {"trending_up", "ranging"}:
        return 1.0
    if normalized == "high_volatility":
        return 0.5
    return 0.0


def _confidence_from_components(
    *,
    votes: dict[str, float],
    composite_score: float,
    volume_ratio: float | None,
    regime: str | None,
) -> float:
    active_votes = [vote for vote in votes.values() if abs(vote) > 1e-9]
    if active_votes and composite_score != 0:
        score_sign = 1 if composite_score > 0 else -1
        agreement_ratio = sum(1 for vote in active_votes if vote * score_sign > 0) / len(active_votes)
    else:
        agreement_ratio = 0.0

    magnitude = min(abs(composite_score), 1.0)
    volume_quality = _volume_quality(volume_ratio)
    direction = "BUY" if composite_score > 0 else "SELL" if composite_score < 0 else "HOLD"
    regime_bonus = _regime_alignment_bonus(regime, direction)
    confidence = (
        agreement_ratio * 0.40
        + magnitude * 0.30
        + volume_quality * 0.20
        + regime_bonus * 0.10
    )
    return max(0.0, min(confidence, 1.0))


def compute_composite_score(
    indicators: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    ai_vote_value: float | None = None,
    regime: str | None = None,
) -> CompositeScoreResult:
    latest_rsi = indicators.get("rsi", [None])[-1] if indicators.get("rsi") else None
    macd_line, signal_line, histogram = indicators.get("macd", ([], [], []))
    latest_volume_ratio = indicators.get("volume_ratio", [None])[-1] if indicators.get("volume_ratio") else None

    rsi_divergence = indicators.get("rsi_divergence")
    votes = {
        "rsi": rsi_vote(latest_rsi, divergence=rsi_divergence),
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
    votes["structure"] = structure_vote(
        indicators.get("sr_levels"),
        indicators.get("latest_close"),
    )

    weights = _resolve_weights(config)
    weighted_sum = sum(votes[key] * weights.get(key, 0.0) for key in votes)
    composite_score = max(min(weighted_sum * dampening_multiplier, 1.0), -1.0)
    confidence = _confidence_from_components(
        votes=votes,
        composite_score=composite_score,
        volume_ratio=latest_volume_ratio,
        regime=regime,
    )

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
        ai_vote_present=False,
    )
