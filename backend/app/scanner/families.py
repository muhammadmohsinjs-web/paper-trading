"""Setup family registry, per-family validators, and regime routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.regime.types import DetailedRegime


class SetupFamily(str, Enum):
    """Broad family grouping for setup types."""

    TREND_CONTINUATION = "trend_continuation"
    MOMENTUM_BREAKOUT = "momentum_breakout"
    MEAN_REVERSION = "mean_reversion"
    VOLATILITY_COMPRESSION = "volatility_compression"


# Maps every known setup_type to its family.
SETUP_TO_FAMILY: dict[str, SetupFamily] = {
    "ema_trend_bullish": SetupFamily.TREND_CONTINUATION,
    "ema_trend_bearish": SetupFamily.TREND_CONTINUATION,
    "sma_crossover_proximity": SetupFamily.TREND_CONTINUATION,
    "adx_strong_trend": SetupFamily.TREND_CONTINUATION,
    "macd_crossover": SetupFamily.MOMENTUM_BREAKOUT,
    "macd_momentum_rising": SetupFamily.MOMENTUM_BREAKOUT,
    "macd_momentum_falling": SetupFamily.MOMENTUM_BREAKOUT,
    "volume_breakout": SetupFamily.MOMENTUM_BREAKOUT,
    "momentum_breakout_high": SetupFamily.MOMENTUM_BREAKOUT,
    "momentum_breakout_low": SetupFamily.MOMENTUM_BREAKOUT,
    "rsi_oversold": SetupFamily.MEAN_REVERSION,
    "rsi_overbought": SetupFamily.MEAN_REVERSION,
    "rsi_divergence_bullish": SetupFamily.MEAN_REVERSION,
    "rsi_divergence_bearish": SetupFamily.MEAN_REVERSION,
    "bb_lower_touch": SetupFamily.MEAN_REVERSION,
    "bb_upper_touch": SetupFamily.MEAN_REVERSION,
    "bb_squeeze": SetupFamily.VOLATILITY_COMPRESSION,
}


# Detailed regimes where each family is allowed to fire.  Anything outside
# this set is either rejected or receives a heavy penalty.
FAMILY_ALLOWED_REGIMES: dict[SetupFamily, set[DetailedRegime]] = {
    SetupFamily.TREND_CONTINUATION: {
        DetailedRegime.CLEAN_TREND_UP,
        DetailedRegime.CLEAN_TREND_DOWN,
        DetailedRegime.VOLATILE_TREND_UP,
        DetailedRegime.VOLATILE_TREND_DOWN,
        DetailedRegime.BREAKOUT_EXPANSION,
    },
    SetupFamily.MOMENTUM_BREAKOUT: {
        DetailedRegime.BREAKOUT_EXPANSION,
        DetailedRegime.CLEAN_TREND_UP,
        DetailedRegime.VOLATILE_TREND_UP,
        DetailedRegime.CLEAN_RANGE,
    },
    SetupFamily.MEAN_REVERSION: {
        DetailedRegime.CLEAN_RANGE,
        DetailedRegime.CHAOTIC_RANGE,
        DetailedRegime.EXHAUSTED_TREND_UP,
        DetailedRegime.EXHAUSTED_TREND_DOWN,
        DetailedRegime.POST_SPIKE_INSTABILITY,
    },
    SetupFamily.VOLATILITY_COMPRESSION: {
        DetailedRegime.CLEAN_RANGE,
        DetailedRegime.CLEAN_TREND_UP,
        DetailedRegime.CLEAN_TREND_DOWN,
    },
}

# Penalty multiplier when a family fires in a non-allowed but not outright
# hostile regime. Hostile regimes (e.g. crash) block entirely.
_HOSTILE_REGIMES: set[DetailedRegime] = {DetailedRegime.CRASH}
_MISMATCHED_PENALTY = 0.55  # multiplied into quality scores


@dataclass
class FamilyValidation:
    """Result of a per-family quality evaluation for a single setup."""

    passed: bool
    family: SetupFamily
    entry_eligible: bool  # False for bearish setups in a long-only engine
    signal_age_bars: int
    symbol_quality_score: float  # overall structural quality [0, 1]
    execution_quality_score: float  # how clean for execution [0, 1]
    room_to_move_score: float  # distance to next resistance/support [0, 1]
    conflict_penalty: float  # deduction for contradictory signals
    freshness_score: float  # 1.0 = brand-new signal, decays
    rejection_reason: str | None = None


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


def resolve_family(setup_type: str) -> SetupFamily | None:
    """Look up the family for a given setup_type string."""
    return SETUP_TO_FAMILY.get(setup_type)


def is_regime_allowed(family: SetupFamily, detailed_regime: DetailedRegime | None) -> bool:
    """Check whether a family is allowed to fire in the given detailed regime."""
    if detailed_regime is None:
        return True  # no detailed info — allow (backward compat)
    if detailed_regime in _HOSTILE_REGIMES:
        return False
    return detailed_regime in FAMILY_ALLOWED_REGIMES.get(family, set())


def regime_penalty(family: SetupFamily, detailed_regime: DetailedRegime | None) -> float:
    """Return a score multiplier: 1.0 if allowed, _MISMATCHED_PENALTY if not, 0.0 if hostile."""
    if detailed_regime is None:
        return 1.0
    if detailed_regime in _HOSTILE_REGIMES:
        return 0.0
    if detailed_regime in FAMILY_ALLOWED_REGIMES.get(family, set()):
        return 1.0
    return _MISMATCHED_PENALTY


# ── Per-family validators ─────────────────────────────────────────────
# Each validator receives raw indicator/metric data and returns a
# FamilyValidation.  The validators are intentionally simple first-pass
# implementations; thresholds can be tuned later.

def validate_trend(
    *,
    setup_type: str,
    signal: str,
    indicators: dict[str, Any],
    tradability_metrics: Any,
    detailed_regime: DetailedRegime | None,
    exhaustion_score: float,
) -> FamilyValidation:
    """Validate a trend-continuation setup."""
    family = SetupFamily.TREND_CONTINUATION
    entry_eligible = signal == "BUY"

    sma_slope = abs(getattr(tradability_metrics, "short_sma_slope_pct_3", 0.0))
    ema_spread = abs(getattr(tradability_metrics, "ema_spread_pct", 0.0))
    atr_pct = getattr(tradability_metrics, "atr_pct_14", 0.0)
    range_pct = getattr(tradability_metrics, "range_pct_20", 0.0)

    # Healthy slope check
    slope_ok = sma_slope >= 0.20
    # Non-exhausted
    fresh_trend = exhaustion_score < 0.65
    # Continuation structure: EMA spread expanding
    structure_ok = ema_spread >= 0.15
    # Non-late entry: ATR shows room
    room = _clamp01(atr_pct / 1.5)

    quality = _clamp01(0.3 * _clamp01(sma_slope / 0.8) + 0.3 * (1.0 - exhaustion_score) + 0.2 * _clamp01(ema_spread / 0.5) + 0.2 * room)
    exec_quality = _clamp01(0.5 * _clamp01(range_pct / 2.0) + 0.5 * _clamp01(atr_pct / 1.0))
    penalty = regime_penalty(family, detailed_regime)

    passed = slope_ok and fresh_trend and structure_ok and penalty > 0
    rejection = None
    if not slope_ok:
        rejection = "Trend slope too weak for continuation"
    elif not fresh_trend:
        rejection = "Trend appears exhausted"
    elif not structure_ok:
        rejection = "EMA structure too compressed"
    elif penalty == 0:
        rejection = "Hostile regime for trend continuation"

    return FamilyValidation(
        passed=passed,
        family=family,
        entry_eligible=entry_eligible,
        signal_age_bars=0,
        symbol_quality_score=round(quality * penalty, 4),
        execution_quality_score=round(exec_quality, 4),
        room_to_move_score=round(room, 4),
        conflict_penalty=0.0,
        freshness_score=1.0,
        rejection_reason=rejection,
    )


def validate_breakout(
    *,
    setup_type: str,
    signal: str,
    indicators: dict[str, Any],
    tradability_metrics: Any,
    detailed_regime: DetailedRegime | None,
    exhaustion_score: float,
) -> FamilyValidation:
    """Validate a momentum-breakout setup."""
    family = SetupFamily.MOMENTUM_BREAKOUT
    entry_eligible = signal == "BUY"

    volume_ratio = getattr(tradability_metrics, "volume_ratio", 0.0)
    atr_pct = getattr(tradability_metrics, "atr_pct_14", 0.0)
    range_pct = getattr(tradability_metrics, "range_pct_20", 0.0)
    displacement = abs(getattr(tradability_metrics, "directional_displacement_pct_10", 0.0))

    # Real expansion
    expansion_ok = atr_pct >= 0.35 and displacement >= 0.50
    # Volume participation
    volume_ok = volume_ratio >= 1.0
    # Breakout room (ATR implies room)
    room = _clamp01(atr_pct / 1.5)
    # Post-breakout cleanliness: displacement vs range
    cleanliness = _clamp01(displacement / max(range_pct, 0.01)) if range_pct > 0 else 0.5

    quality = _clamp01(0.30 * _clamp01(displacement / 1.5) + 0.25 * _clamp01(volume_ratio / 2.0) + 0.25 * room + 0.20 * cleanliness)
    exec_quality = _clamp01(0.5 * _clamp01(volume_ratio / 1.5) + 0.5 * _clamp01(atr_pct / 1.0))
    penalty = regime_penalty(family, detailed_regime)

    passed = expansion_ok and volume_ok and penalty > 0
    rejection = None
    if not expansion_ok:
        rejection = "Insufficient expansion for breakout"
    elif not volume_ok:
        rejection = "Volume participation too low"
    elif penalty == 0:
        rejection = "Hostile regime for breakout"

    return FamilyValidation(
        passed=passed,
        family=family,
        entry_eligible=entry_eligible,
        signal_age_bars=0,
        symbol_quality_score=round(quality * penalty, 4),
        execution_quality_score=round(exec_quality, 4),
        room_to_move_score=round(room, 4),
        conflict_penalty=0.0,
        freshness_score=1.0,
        rejection_reason=rejection,
    )


def validate_mean_reversion(
    *,
    setup_type: str,
    signal: str,
    indicators: dict[str, Any],
    tradability_metrics: Any,
    detailed_regime: DetailedRegime | None,
    exhaustion_score: float,
) -> FamilyValidation:
    """Validate a mean-reversion setup."""
    family = SetupFamily.MEAN_REVERSION
    entry_eligible = signal == "BUY"

    rsi_values = indicators.get("rsi", [])
    latest_rsi = float(rsi_values[-1]) if rsi_values else 50.0
    bb_width_pct = getattr(tradability_metrics, "bb_width_pct", 0.0)
    atr_pct = getattr(tradability_metrics, "atr_pct_14", 0.0)
    range_pct = getattr(tradability_metrics, "range_pct_20", 0.0)

    # Stretch into support/discount (for BUY) or resistance (for SELL)
    if signal == "BUY":
        stretch_ok = latest_rsi < 40
    else:
        stretch_ok = latest_rsi > 60

    # Reversal evidence: RSI turning from extreme
    if len(rsi_values) >= 3:
        if signal == "BUY":
            reversal_evidence = rsi_values[-1] > rsi_values[-2] and rsi_values[-2] <= rsi_values[-3]
        else:
            reversal_evidence = rsi_values[-1] < rsi_values[-2] and rsi_values[-2] >= rsi_values[-3]
    else:
        reversal_evidence = False

    # No hostile trend regime
    penalty = regime_penalty(family, detailed_regime)
    hostile_trend = detailed_regime in {
        DetailedRegime.CLEAN_TREND_UP,
        DetailedRegime.CLEAN_TREND_DOWN,
        DetailedRegime.VOLATILE_TREND_UP,
        DetailedRegime.VOLATILE_TREND_DOWN,
        DetailedRegime.BREAKOUT_EXPANSION,
    } if detailed_regime is not None else False

    room = _clamp01(bb_width_pct / 3.0)
    quality = _clamp01(
        0.30 * _clamp01(abs(latest_rsi - 50) / 30)
        + 0.25 * (1.0 if reversal_evidence else 0.3)
        + 0.25 * room
        + 0.20 * _clamp01(atr_pct / 0.8)
    )
    exec_quality = _clamp01(0.5 * _clamp01(range_pct / 2.0) + 0.5 * _clamp01(atr_pct / 1.0))

    passed = stretch_ok and not hostile_trend and penalty > 0
    rejection = None
    if not stretch_ok:
        rejection = "Insufficient stretch for mean reversion"
    elif hostile_trend:
        rejection = "Active trend regime hostile to mean reversion"
    elif penalty == 0:
        rejection = "Hostile regime for mean reversion"

    return FamilyValidation(
        passed=passed,
        family=family,
        entry_eligible=entry_eligible,
        signal_age_bars=0,
        symbol_quality_score=round(quality * penalty, 4),
        execution_quality_score=round(exec_quality, 4),
        room_to_move_score=round(room, 4),
        conflict_penalty=0.0,
        freshness_score=1.0,
        rejection_reason=rejection,
    )


def validate_compression(
    *,
    setup_type: str,
    signal: str,
    indicators: dict[str, Any],
    tradability_metrics: Any,
    detailed_regime: DetailedRegime | None,
    exhaustion_score: float,
) -> FamilyValidation:
    """Validate a volatility-compression setup."""
    family = SetupFamily.VOLATILITY_COMPRESSION
    entry_eligible = signal == "BUY"

    bb_width_pct = getattr(tradability_metrics, "bb_width_pct", 0.0)
    close_std = getattr(tradability_metrics, "close_std_pct_24h", 0.0)
    atr_pct = getattr(tradability_metrics, "atr_pct_14", 0.0)
    range_pct = getattr(tradability_metrics, "range_pct_20", 0.0)

    # Clean squeeze: BB width is narrow but not dead
    squeeze_ok = bb_width_pct >= 0.80
    # Non-flat compression: std shows some life
    not_flat = close_std >= 0.20
    # Expansion path: ATR suggests potential
    expansion_path = atr_pct >= 0.25

    room = _clamp01(atr_pct / 1.0)
    quality = _clamp01(
        0.35 * (1.0 if squeeze_ok else 0.2)
        + 0.25 * _clamp01(close_std / 0.5)
        + 0.20 * _clamp01(atr_pct / 0.8)
        + 0.20 * _clamp01(range_pct / 1.5)
    )
    exec_quality = _clamp01(0.5 * _clamp01(range_pct / 1.5) + 0.5 * _clamp01(atr_pct / 0.8))
    penalty = regime_penalty(family, detailed_regime)

    passed = squeeze_ok and not_flat and expansion_path and penalty > 0
    rejection = None
    if not squeeze_ok:
        rejection = "Bollinger width too narrow for valid compression"
    elif not not_flat:
        rejection = "Compression is too flat to support expansion"
    elif not expansion_path:
        rejection = "ATR too low for expansion potential"
    elif penalty == 0:
        rejection = "Hostile regime for compression"

    return FamilyValidation(
        passed=passed,
        family=family,
        entry_eligible=entry_eligible,
        signal_age_bars=0,
        symbol_quality_score=round(quality * penalty, 4),
        execution_quality_score=round(exec_quality, 4),
        room_to_move_score=round(room, 4),
        conflict_penalty=0.0,
        freshness_score=1.0,
        rejection_reason=rejection,
    )


# Dispatch table
_FAMILY_VALIDATORS = {
    SetupFamily.TREND_CONTINUATION: validate_trend,
    SetupFamily.MOMENTUM_BREAKOUT: validate_breakout,
    SetupFamily.MEAN_REVERSION: validate_mean_reversion,
    SetupFamily.VOLATILITY_COMPRESSION: validate_compression,
}


def validate_setup_family(
    *,
    setup_type: str,
    signal: str,
    indicators: dict[str, Any],
    tradability_metrics: Any,
    detailed_regime: DetailedRegime | None,
    exhaustion_score: float,
) -> FamilyValidation | None:
    """Run the appropriate family validator for the given setup_type.

    Returns None if the setup_type is not mapped to a known family.
    """
    family = resolve_family(setup_type)
    if family is None:
        return None
    validator = _FAMILY_VALIDATORS.get(family)
    if validator is None:
        return None
    return validator(
        setup_type=setup_type,
        signal=signal,
        indicators=indicators,
        tradability_metrics=tradability_metrics,
        detailed_regime=detailed_regime,
        exhaustion_score=exhaustion_score,
    )
