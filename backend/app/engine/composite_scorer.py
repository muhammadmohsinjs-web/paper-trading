"""Composite signal scoring for the hybrid trading strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.engine.reason_codes import (
    ATR_BELOW_HARD_FLOOR,
    DIRECTIONAL_SCORE_TOO_SMALL,
    EDGE_TOO_WEAK,
    FINAL_CONFIDENCE_TOO_LOW,
    MARKET_QUALITY_TOO_LOW,
    MOVEMENT_QUALITY_TOO_LOW,
)
from app.engine.trade_quality import resolve_trade_quality_thresholds

DEFAULT_WEIGHTS = {
    "rsi": 0.20,
    "macd": 0.20,
    "sma": 0.10,
    "ema": 0.10,
    "volume": 0.25,
    "structure": 0.15,
}

DEFAULT_CONFIDENCE_GATE = 0.35
DEFAULT_VOLUME_DAMPENING_MULTIPLIER = 0.7


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
    directional_score: float
    edge_strength: float
    base_edge_score: float
    signal_agreement: float
    market_quality: float
    regime_alignment: float
    edge_floor_passed: bool
    quality_floor_passed: bool
    reject_reason_codes: list[str]


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
    return 0.0, 1.0


def structure_vote(sr_levels: list | None, latest_close: float | None) -> float:
    if not sr_levels or latest_close is None:
        return 0.0

    from app.market.structure import nearest_resistance, nearest_support

    nearest_sup = nearest_support(sr_levels, latest_close)
    nearest_res = nearest_resistance(sr_levels, latest_close)
    vote = 0.0

    if nearest_sup is not None:
        distance_pct = (latest_close - nearest_sup.price) / latest_close * 100
        if distance_pct < 1.0:
            vote += 0.5 * min(nearest_sup.strength / 5.0, 1.0)
    if nearest_res is not None:
        distance_pct = (nearest_res.price - latest_close) / latest_close * 100
        if distance_pct < 1.0:
            vote -= 0.5 * min(nearest_res.strength / 5.0, 1.0)
    return max(-1.0, min(1.0, vote))


def compute_ai_vote(bias: float | None, confidence: float | None, freshness_decay: float | None) -> float | None:
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
    if volume_ratio >= 0.8:
        return 0.5
    if volume_ratio >= 0.5:
        return 0.2
    return 0.0


def _derive_market_quality(indicators: dict[str, Any], explicit_score: float | None) -> float:
    if explicit_score is not None:
        return max(0.0, min(explicit_score, 1.0))
    if "market_quality_score" in indicators:
        return max(0.0, min(float(indicators["market_quality_score"]), 1.0))

    latest_close = indicators.get("latest_close") or 0.0
    atr_values = indicators.get("atr", [])
    atr_pct = 0.0
    if latest_close and atr_values:
        atr_pct = float(atr_values[-1]) / float(latest_close) * 100.0
    atr_score = 0.6 if not atr_values else max(0.0, min((atr_pct - 0.2) / 0.6, 1.0))
    return max(0.0, min(0.65 * atr_score + 0.35 * _volume_quality(indicators.get("volume_ratio", [None])[-1] if indicators.get("volume_ratio") else None), 1.0))


def _derive_movement_quality(indicators: dict[str, Any], explicit_score: float | None) -> float:
    if explicit_score is not None:
        return max(0.0, min(explicit_score, 1.0))
    if "movement_quality_score" in indicators:
        return max(0.0, min(float(indicators["movement_quality_score"]), 1.0))

    latest_close = indicators.get("latest_close") or 0.0
    previous_close = indicators.get("previous_close") or latest_close
    atr_values = indicators.get("atr", [])
    atr_pct = 0.0
    if latest_close and atr_values:
        atr_pct = float(atr_values[-1]) / float(latest_close) * 100.0
    displacement = abs((float(latest_close) - float(previous_close)) / float(previous_close) * 100.0) if previous_close else 0.0
    atr_score = 0.6 if not atr_values else max(0.0, min((atr_pct - 0.2) / 0.7, 1.0))
    displacement_score = max(0.0, min((displacement - 0.15) / 0.5, 1.0))
    return max(0.0, min(0.60 * atr_score + 0.40 * displacement_score, 1.0))


def _regime_alignment_score(regime: str | None, direction: str) -> float:
    normalized = (regime or "").strip().lower()
    if direction == "BUY":
        if normalized == "trending_up":
            return 1.0
        if normalized == "ranging":
            return 0.8
        if normalized == "high_volatility":
            return 0.4
        return 0.2
    if direction == "SELL":
        if normalized == "trending_down":
            return 1.0
        if normalized == "high_volatility":
            return 0.7
        return 0.3
    return 0.0


def _signal_agreement(votes: dict[str, float], directional_score: float) -> float:
    active_votes = [vote for vote in votes.values() if abs(vote) > 1e-9]
    if not active_votes or abs(directional_score) <= 1e-9:
        return 0.0
    score_sign = 1 if directional_score > 0 else -1
    return sum(1 for vote in active_votes if vote * score_sign > 0) / len(active_votes)


def compute_composite_score(
    indicators: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    ai_vote_value: float | None = None,
    regime: str | None = None,
    movement_quality_score: float | None = None,
    market_quality_score: float | None = None,
) -> CompositeScoreResult:
    thresholds = resolve_trade_quality_thresholds(config)

    # Hard ATR floor: reject assets with insufficient price movement to
    # trade profitably after fees/slippage (catches stablecoins, pegged
    # tokens, and any ultra-low-volatility asset regardless of denylist).
    _HARD_ATR_FLOOR_PCT = 0.10
    atr_values = indicators.get("atr", [])
    _latest_close = indicators.get("latest_close")
    if atr_values and _latest_close and _latest_close > 0:
        _latest_atr_pct = (atr_values[-1] / _latest_close) * 100
        if _latest_atr_pct < _HARD_ATR_FLOOR_PCT:
            return CompositeScoreResult(
                votes={},
                weights={},
                composite_score=0.0,
                confidence=0.0,
                direction="HOLD",
                signal="HOLD",
                dampening_multiplier=1.0,
                ai_vote_present=ai_vote_value is not None,
                directional_score=0.0,
                edge_strength=0.0,
                base_edge_score=0.0,
                signal_agreement=0.0,
                market_quality=0.0,
                regime_alignment=0.0,
                edge_floor_passed=False,
                quality_floor_passed=False,
                reject_reason_codes=[ATR_BELOW_HARD_FLOOR],
            )

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
    votes["structure"] = structure_vote(indicators.get("sr_levels"), indicators.get("latest_close"))

    weights = _resolve_weights(config)
    weighted_sum = sum(votes[key] * weights.get(key, 0.0) for key in votes)
    directional_score = max(min(weighted_sum * dampening_multiplier, 1.0), -1.0)
    composite_score = directional_score

    if composite_score > 0:
        direction = "BUY"
    elif composite_score < 0:
        direction = "SELL"
    else:
        direction = "HOLD"

    movement_quality = _derive_movement_quality(indicators, movement_quality_score)
    market_quality = _derive_market_quality(indicators, market_quality_score)
    signal_agreement = _signal_agreement(votes, directional_score)
    regime_alignment = _regime_alignment_score(regime, direction)
    base_edge_score = min(
        1.0,
        0.70 * abs(directional_score)
        + 0.20 * movement_quality
        + 0.10 * market_quality,
    )
    agreement_multiplier = 0.85 + (0.20 * signal_agreement)
    regime_multiplier = 0.90 + (0.10 * regime_alignment)
    edge_strength = min(base_edge_score, 1.0)
    confidence = max(0.0, min(edge_strength * agreement_multiplier * regime_multiplier, 1.0))

    reject_reason_codes: list[str] = []
    edge_floor_passed = abs(directional_score) >= thresholds.min_directional_score and edge_strength >= thresholds.min_edge_strength
    quality_grace = 0.05
    strong_confirmation = (
        abs(directional_score) >= (thresholds.min_directional_score + 0.08)
        and signal_agreement >= 0.66
        and edge_strength >= thresholds.min_edge_strength
    )
    movement_quality_failed = (
        movement_quality < thresholds.min_movement_quality_score
        and not (
            strong_confirmation
            and movement_quality >= (thresholds.min_movement_quality_score - quality_grace)
        )
    )
    market_quality_failed = (
        market_quality < thresholds.min_composite_market_quality_score
        and not (
            strong_confirmation
            and market_quality >= (thresholds.min_composite_market_quality_score - quality_grace)
        )
    )
    quality_floor_passed = not movement_quality_failed and not market_quality_failed
    if abs(directional_score) < thresholds.min_directional_score:
        reject_reason_codes.append(DIRECTIONAL_SCORE_TOO_SMALL)
    if movement_quality_failed:
        reject_reason_codes.append(MOVEMENT_QUALITY_TOO_LOW)
    if market_quality_failed:
        reject_reason_codes.append(MARKET_QUALITY_TOO_LOW)
    if edge_strength < thresholds.min_edge_strength:
        reject_reason_codes.append(EDGE_TOO_WEAK)

    confidence_floor = max(0.45, thresholds.min_edge_strength - 0.05)
    gate = max(float((config or {}).get("confidence_gate", DEFAULT_CONFIDENCE_GATE)), confidence_floor)
    if confidence < gate:
        reject_reason_codes.append(FINAL_CONFIDENCE_TOO_LOW)

    signal = direction if direction != "HOLD" and not reject_reason_codes else "HOLD"

    return CompositeScoreResult(
        votes=votes,
        weights=weights,
        composite_score=composite_score,
        confidence=confidence,
        direction=direction,
        signal=signal,
        dampening_multiplier=dampening_multiplier,
        ai_vote_present=ai_vote_value is not None,
        directional_score=directional_score,
        edge_strength=edge_strength,
        base_edge_score=base_edge_score,
        signal_agreement=signal_agreement,
        market_quality=market_quality,
        regime_alignment=regime_alignment,
        edge_floor_passed=edge_floor_passed,
        quality_floor_passed=quality_floor_passed,
        reject_reason_codes=reject_reason_codes,
    )
