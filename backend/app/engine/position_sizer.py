"""ATR-based position sizing for the hybrid strategy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.engine.reason_codes import (
    ATR_TOO_SMALL_FOR_SIZING,
    STOP_DISTANCE_TOO_SMALL,
    TARGET_DISTANCE_TOO_SMALL,
)
from app.engine.trade_quality import resolve_trade_quality_thresholds

CONFIDENCE_MULTIPLIERS = {
    "full": Decimal("1.0"),
    "reduced": Decimal("0.7"),
    "small": Decimal("0.4"),
}


@dataclass(frozen=True)
class PositionSizingResult:
    quantity_pct: Decimal
    stop_loss_price: Decimal
    take_profit_price: Decimal
    risk_amount: Decimal
    position_value: Decimal
    stop_distance: Decimal
    stop_distance_pct: Decimal
    confidence_multiplier: Decimal
    streak_multiplier: Decimal
    entry_atr: Decimal


@dataclass(frozen=True)
class ScaledExitLevels:
    stop_loss_price: Decimal
    take_profit_1_price: Decimal  # 1:1 R:R
    take_profit_2_price: Decimal  # 2:1 R:R
    take_profit_3_price: Decimal  # 3:1 R:R


@dataclass(frozen=True)
class PositionSizingSafetyResult:
    passed: bool
    reason_code: str | None
    reason_text: str
    atr_pct: Decimal
    stop_distance_pct: Decimal
    take_profit_distance_pct: Decimal
    min_atr_pct: Decimal
    min_stop_distance_pct: Decimal
    min_take_profit_distance_pct: Decimal


def calculate_exit_levels(
    *,
    entry_price: Decimal,
    atr: Decimal,
    atr_multiplier: Decimal = Decimal("2.0"),
    take_profit_ratio: Decimal = Decimal("2.0"),
) -> tuple[Decimal, Decimal]:
    """Legacy 2-tuple return for backward compatibility."""
    stop_distance = atr * atr_multiplier
    stop_loss_price = (entry_price - stop_distance).quantize(Decimal("0.00000001"))
    take_profit_price = (
        entry_price + (stop_distance * take_profit_ratio)
    ).quantize(Decimal("0.00000001"))
    return stop_loss_price, take_profit_price


def calculate_scaled_exit_levels(
    *,
    entry_price: Decimal,
    atr: Decimal,
    atr_multiplier: Decimal = Decimal("2.0"),
) -> ScaledExitLevels:
    """Compute stop-loss and three take-profit levels at 1:1, 2:1, 3:1 R:R."""
    stop_distance = atr * atr_multiplier
    q = Decimal("0.00000001")
    return ScaledExitLevels(
        stop_loss_price=(entry_price - stop_distance).quantize(q),
        take_profit_1_price=(entry_price + stop_distance * Decimal("1")).quantize(q),
        take_profit_2_price=(entry_price + stop_distance * Decimal("2")).quantize(q),
        take_profit_3_price=(entry_price + stop_distance * Decimal("3")).quantize(q),
    )


def streak_multiplier_for_losses(losing_streak_count: int) -> Decimal:
    if losing_streak_count >= 5:
        return Decimal("0.25")
    if losing_streak_count >= 3:
        return Decimal("0.50")
    return Decimal("1.0")


def calculate_position_size(
    *,
    equity: Decimal,
    entry_price: Decimal,
    atr: Decimal,
    atr_multiplier: Decimal = Decimal("2.0"),
    risk_per_trade_pct: Decimal = Decimal("2.0"),
    confidence_tier: str = "full",
    losing_streak_count: int = 0,
    max_position_pct: Decimal = Decimal("30.0"),
    take_profit_ratio: Decimal = Decimal("2.0"),
) -> PositionSizingResult:
    if equity <= 0 or entry_price <= 0 or atr <= 0 or atr_multiplier <= 0:
        zero = Decimal("0")
        return PositionSizingResult(
            quantity_pct=zero,
            stop_loss_price=entry_price,
            take_profit_price=entry_price,
            risk_amount=zero,
            position_value=zero,
            stop_distance=zero,
            stop_distance_pct=zero,
            confidence_multiplier=CONFIDENCE_MULTIPLIERS.get(confidence_tier, Decimal("1.0")),
            streak_multiplier=streak_multiplier_for_losses(losing_streak_count),
            entry_atr=atr,
        )

    stop_distance = atr * atr_multiplier
    stop_distance_pct = stop_distance / entry_price
    stop_loss_price, take_profit_price = calculate_exit_levels(
        entry_price=entry_price,
        atr=atr,
        atr_multiplier=atr_multiplier,
        take_profit_ratio=take_profit_ratio,
    )
    risk_amount = equity * (risk_per_trade_pct / Decimal("100"))
    confidence_multiplier = CONFIDENCE_MULTIPLIERS.get(confidence_tier, Decimal("1.0"))
    streak_multiplier = streak_multiplier_for_losses(losing_streak_count)
    adjusted_risk = risk_amount * confidence_multiplier * streak_multiplier

    if stop_distance_pct <= 0:
        position_value = Decimal("0")
    else:
        position_value = adjusted_risk / stop_distance_pct

    max_position_value = equity * (max_position_pct / Decimal("100"))
    if confidence_tier == "full":
        # High-conviction: use up to 60% of available equity, but respect max_position_pct
        final_position_value = min(position_value, equity * Decimal("0.6"), max_position_value)
    else:
        final_position_value = min(position_value, max_position_value)
    quantity_pct = final_position_value / equity if equity > 0 else Decimal("0")
    quantity_pct = max(Decimal("0"), min(quantity_pct, Decimal("1.0")))

    return PositionSizingResult(
        quantity_pct=quantity_pct,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        risk_amount=adjusted_risk.quantize(Decimal("0.00000001")),
        position_value=final_position_value.quantize(Decimal("0.00000001")),
        stop_distance=stop_distance.quantize(Decimal("0.00000001")),
        stop_distance_pct=stop_distance_pct.quantize(Decimal("0.00000001")),
        confidence_multiplier=confidence_multiplier,
        streak_multiplier=streak_multiplier,
        entry_atr=atr.quantize(Decimal("0.00000001")),
    )


def evaluate_position_sizing_safety(
    *,
    entry_price: Decimal,
    sizing: PositionSizingResult,
    total_round_trip_cost_pct: Decimal,
    config: dict | None = None,
) -> PositionSizingSafetyResult:
    thresholds = resolve_trade_quality_thresholds(config)
    if entry_price <= 0:
        return PositionSizingSafetyResult(
            passed=False,
            reason_code=ATR_TOO_SMALL_FOR_SIZING,
            reason_text="Entry price is invalid for sizing safety checks",
            atr_pct=Decimal("0"),
            stop_distance_pct=Decimal("0"),
            take_profit_distance_pct=Decimal("0"),
            min_atr_pct=Decimal(str(thresholds.min_atr_pct)),
            min_stop_distance_pct=Decimal(str(thresholds.min_stop_distance_pct)),
            min_take_profit_distance_pct=Decimal(str(thresholds.min_take_profit_distance_pct)),
        )

    atr_pct = (sizing.entry_atr / entry_price) * Decimal("100")
    stop_distance_pct = sizing.stop_distance_pct * Decimal("100")
    take_profit_distance_pct = ((sizing.take_profit_price - entry_price) / entry_price) * Decimal("100")
    min_atr_pct = max(Decimal(str(thresholds.min_atr_pct)), total_round_trip_cost_pct * Decimal("1.25"))
    min_stop_distance_pct = max(Decimal(str(thresholds.min_stop_distance_pct)), total_round_trip_cost_pct * Decimal("1.5"))
    min_take_profit_distance_pct = max(Decimal(str(thresholds.min_take_profit_distance_pct)), total_round_trip_cost_pct * Decimal("2.0"))

    if atr_pct < min_atr_pct:
        return PositionSizingSafetyResult(
            passed=False,
            reason_code=ATR_TOO_SMALL_FOR_SIZING,
            reason_text="ATR percent is below the minimum safety floor",
            atr_pct=atr_pct.quantize(Decimal("0.0001")),
            stop_distance_pct=stop_distance_pct.quantize(Decimal("0.0001")),
            take_profit_distance_pct=take_profit_distance_pct.quantize(Decimal("0.0001")),
            min_atr_pct=min_atr_pct.quantize(Decimal("0.0001")),
            min_stop_distance_pct=min_stop_distance_pct.quantize(Decimal("0.0001")),
            min_take_profit_distance_pct=min_take_profit_distance_pct.quantize(Decimal("0.0001")),
        )
    if stop_distance_pct < min_stop_distance_pct:
        return PositionSizingSafetyResult(
            passed=False,
            reason_code=STOP_DISTANCE_TOO_SMALL,
            reason_text="Stop distance is too small relative to total trading costs",
            atr_pct=atr_pct.quantize(Decimal("0.0001")),
            stop_distance_pct=stop_distance_pct.quantize(Decimal("0.0001")),
            take_profit_distance_pct=take_profit_distance_pct.quantize(Decimal("0.0001")),
            min_atr_pct=min_atr_pct.quantize(Decimal("0.0001")),
            min_stop_distance_pct=min_stop_distance_pct.quantize(Decimal("0.0001")),
            min_take_profit_distance_pct=min_take_profit_distance_pct.quantize(Decimal("0.0001")),
        )
    if take_profit_distance_pct < min_take_profit_distance_pct:
        return PositionSizingSafetyResult(
            passed=False,
            reason_code=TARGET_DISTANCE_TOO_SMALL,
            reason_text="Take-profit distance is too small relative to total trading costs",
            atr_pct=atr_pct.quantize(Decimal("0.0001")),
            stop_distance_pct=stop_distance_pct.quantize(Decimal("0.0001")),
            take_profit_distance_pct=take_profit_distance_pct.quantize(Decimal("0.0001")),
            min_atr_pct=min_atr_pct.quantize(Decimal("0.0001")),
            min_stop_distance_pct=min_stop_distance_pct.quantize(Decimal("0.0001")),
            min_take_profit_distance_pct=min_take_profit_distance_pct.quantize(Decimal("0.0001")),
        )

    return PositionSizingSafetyResult(
        passed=True,
        reason_code=None,
        reason_text="Sizing safety checks passed",
        atr_pct=atr_pct.quantize(Decimal("0.0001")),
        stop_distance_pct=stop_distance_pct.quantize(Decimal("0.0001")),
        take_profit_distance_pct=take_profit_distance_pct.quantize(Decimal("0.0001")),
        min_atr_pct=min_atr_pct.quantize(Decimal("0.0001")),
        min_stop_distance_pct=min_stop_distance_pct.quantize(Decimal("0.0001")),
        min_take_profit_distance_pct=min_take_profit_distance_pct.quantize(Decimal("0.0001")),
    )
