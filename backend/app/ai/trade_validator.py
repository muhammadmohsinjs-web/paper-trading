"""AI trade validation — secondary intelligence layer for signal quality filtering.

AI acts as an advisor that can reduce confidence or veto trades,
but CANNOT generate trades that the algorithm did not produce.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Confidence adjustment bounds — AI validation can only reduce confidence.
MAX_CONFIDENCE_BOOST = 0.0
MAX_CONFIDENCE_REDUCTION = 0.3


@dataclass
class ValidationResult:
    """Output of AI trade validation."""

    approved: bool
    confidence_adjustment: float  # clamped to [-0.3, +0.0]
    reason: str
    original_confidence: float
    adjusted_confidence: float


def validate_trade_signal(
    signal_action: str,
    signal_confidence: float,
    indicators: dict[str, Any],
    regime: str,
    recent_trades: list[dict[str, Any]] | None = None,
    ai_response: dict[str, Any] | None = None,
) -> ValidationResult:
    """Validate a trade signal using AI response or rule-based fallback.

    When AI is unavailable, applies rule-based validation:
    - Regime misalignment reduces confidence
    - Low volume reduces confidence
    - Recent consecutive losses reduce confidence
    """
    if ai_response is not None:
        return _process_ai_validation(signal_confidence, ai_response)

    return _rule_based_validation(
        signal_action, signal_confidence, indicators, regime, recent_trades
    )


def _process_ai_validation(
    signal_confidence: float,
    ai_response: dict[str, Any],
) -> ValidationResult:
    """Process AI validation response with strict bounds."""
    approved = ai_response.get("approve", True)
    raw_adjustment = float(ai_response.get("confidence_adjustment", 0.0))
    reason = ai_response.get("reason", "AI validation")

    # Clamp adjustment to safe range
    adjustment = max(-MAX_CONFIDENCE_REDUCTION, min(MAX_CONFIDENCE_BOOST, raw_adjustment))
    adjusted = max(0.0, min(1.0, signal_confidence + adjustment))

    # If AI says reject, set confidence to 0
    if not approved:
        adjusted = 0.0
        adjustment = -signal_confidence

    return ValidationResult(
        approved=approved,
        confidence_adjustment=round(adjustment, 4),
        reason=reason,
        original_confidence=signal_confidence,
        adjusted_confidence=round(adjusted, 4),
    )


def _rule_based_validation(
    signal_action: str,
    signal_confidence: float,
    indicators: dict[str, Any],
    regime: str,
    recent_trades: list[dict[str, Any]] | None = None,
) -> ValidationResult:
    """Rule-based trade validation when AI is unavailable."""
    adjustment = 0.0
    reasons: list[str] = []

    # Check 1: Regime misalignment
    if signal_action == "BUY" and regime == "crash":
        return ValidationResult(
            approved=False,
            confidence_adjustment=-signal_confidence,
            reason="BUY signal rejected in CRASH regime",
            original_confidence=signal_confidence,
            adjusted_confidence=0.0,
        )

    if signal_action == "BUY" and regime == "high_volatility":
        adjustment -= 0.15
        reasons.append("High volatility regime reduces BUY confidence")

    if signal_action == "BUY" and regime == "trending_down":
        adjustment -= 0.10
        reasons.append("Trending down regime reduces BUY confidence")

    # Check 2: Low volume
    volume_ratio_values = indicators.get("volume_ratio", [])
    if volume_ratio_values:
        latest_vol = volume_ratio_values[-1] if isinstance(volume_ratio_values, list) else volume_ratio_values
        if latest_vol < 0.5:
            adjustment -= 0.10
            reasons.append(f"Low volume ({latest_vol:.2f}x avg)")

    # Check 3: Recent losses streak
    if recent_trades:
        recent_pnls = [t.get("pnl", 0) for t in recent_trades[-5:] if t.get("pnl") is not None]
        consecutive_losses = 0
        for pnl in reversed(recent_pnls):
            if pnl < 0:
                consecutive_losses += 1
            else:
                break
        if consecutive_losses >= 3:
            adjustment -= 0.10
            reasons.append(f"{consecutive_losses} consecutive losses")

    # Clamp
    adjustment = max(-MAX_CONFIDENCE_REDUCTION, min(MAX_CONFIDENCE_BOOST, adjustment))
    adjusted = max(0.0, min(1.0, signal_confidence + adjustment))
    approved = adjusted > 0.05  # reject if confidence drops too low

    return ValidationResult(
        approved=approved,
        confidence_adjustment=round(adjustment, 4),
        reason="; ".join(reasons) if reasons else "All validation checks passed",
        original_confidence=signal_confidence,
        adjusted_confidence=round(adjusted, 4),
    )
