"""Post-trade attribution — analyzes why trades won or lost."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TradeAttribution:
    """Attribution analysis for a completed trade."""

    trade_id: str
    primary_factor: str
    secondary_factors: list[str] = field(default_factory=list)
    entry_regime: str = "unknown"
    exit_regime: str = "unknown"
    holding_hours: float = 0.0
    entry_indicators: dict[str, Any] = field(default_factory=dict)
    exit_indicators: dict[str, Any] = field(default_factory=dict)
    pnl: float = 0.0
    lesson: str = ""


def attribute_trade(
    trade_id: str,
    entry_indicators: dict[str, Any],
    exit_indicators: dict[str, Any],
    entry_regime: str,
    exit_regime: str,
    pnl: float,
    holding_hours: float,
    decision_source: str,
) -> TradeAttribution:
    """Analyze a completed trade and attribute its outcome.

    Pure rule-based analysis — no AI calls (AI attribution is optional, done separately).
    """
    factors: list[str] = []
    primary_factor = "unknown"

    is_win = pnl > 0

    # Factor 1: Regime change during trade
    if entry_regime != exit_regime:
        factors.append(f"regime_shift:{entry_regime}->{exit_regime}")
        if not is_win:
            primary_factor = "regime_change"

    # Factor 2: Volume confirmation
    entry_vol = _extract_value(entry_indicators, "volume_ratio")
    exit_vol = _extract_value(exit_indicators, "volume_ratio")
    if entry_vol is not None:
        if entry_vol < 0.7:
            factors.append("weak_entry_volume")
            if not is_win and primary_factor == "unknown":
                primary_factor = "low_volume_entry"
        elif entry_vol > 1.5:
            factors.append("strong_entry_volume")

    # Factor 3: RSI extremes
    entry_rsi = _extract_value(entry_indicators, "rsi")
    exit_rsi = _extract_value(exit_indicators, "rsi")
    if entry_rsi is not None:
        if entry_rsi < 25:
            factors.append("extreme_oversold_entry")
        elif entry_rsi > 75:
            factors.append("extreme_overbought_entry")

    # Factor 4: ATR-based stop distance
    entry_atr = _extract_value(entry_indicators, "atr")
    if entry_atr is not None and entry_atr > 0:
        entry_close = _extract_value(entry_indicators, "latest_close") or 1
        atr_pct = entry_atr / entry_close * 100
        if atr_pct > 5:
            factors.append("high_volatility_entry")
        elif atr_pct < 1:
            factors.append("low_volatility_entry")

    # Factor 5: Holding duration
    if holding_hours > 48:
        factors.append("extended_hold")
        if not is_win and primary_factor == "unknown":
            primary_factor = "time_decay"
    elif holding_hours < 1:
        factors.append("quick_trade")

    # Factor 6: Decision source
    factors.append(f"source:{decision_source}")

    # Determine primary factor if still unknown
    if primary_factor == "unknown":
        if is_win:
            if entry_vol and entry_vol > 1.5:
                primary_factor = "volume_confirmed_entry"
            elif entry_rsi and entry_rsi < 30:
                primary_factor = "oversold_reversal"
            else:
                primary_factor = "signal_quality"
        else:
            primary_factor = "adverse_price_movement"

    # Generate lesson
    lesson = _generate_lesson(primary_factor, is_win, factors)

    return TradeAttribution(
        trade_id=trade_id,
        primary_factor=primary_factor,
        secondary_factors=factors,
        entry_regime=entry_regime,
        exit_regime=exit_regime,
        holding_hours=round(holding_hours, 2),
        entry_indicators=entry_indicators,
        exit_indicators=exit_indicators,
        pnl=round(pnl, 4),
        lesson=lesson,
    )


def _extract_value(indicators: dict[str, Any], key: str) -> float | None:
    """Extract a single float from indicators (handles lists and scalars)."""
    val = indicators.get(key)
    if val is None:
        return None
    if isinstance(val, (list, tuple)):
        return float(val[-1]) if val else None
    return float(val)


def _generate_lesson(primary_factor: str, is_win: bool, factors: list[str]) -> str:
    """Generate a concise lesson from the attribution."""
    lessons = {
        "regime_change": "Regime shifted during trade. Consider tighter stops or shorter holds when regime is unstable.",
        "low_volume_entry": "Entered on weak volume. Require volume ratio > 1.0 for higher-conviction entries.",
        "time_decay": "Held too long without price movement. Review time-stop settings.",
        "adverse_price_movement": "Price moved against position. Check if entry was well-timed.",
        "volume_confirmed_entry": "Strong volume at entry confirmed the move. Good signal quality.",
        "oversold_reversal": "Caught an oversold bounce. RSI mean reversion worked well here.",
        "signal_quality": "Signal was accurate. Standard profitable trade.",
    }
    return lessons.get(primary_factor, f"{'Profitable' if is_win else 'Losing'} trade attributed to: {primary_factor}")
