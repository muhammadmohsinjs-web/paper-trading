"""ATR-based position sizing for the hybrid strategy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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
    stop_loss_price = entry_price - stop_distance
    take_profit_price = entry_price + (stop_distance * take_profit_ratio)
    risk_amount = equity * (risk_per_trade_pct / Decimal("100"))
    confidence_multiplier = CONFIDENCE_MULTIPLIERS.get(confidence_tier, Decimal("1.0"))
    streak_multiplier = streak_multiplier_for_losses(losing_streak_count)
    adjusted_risk = risk_amount * confidence_multiplier * streak_multiplier

    if stop_distance_pct <= 0:
        position_value = Decimal("0")
    else:
        position_value = adjusted_risk / stop_distance_pct

    max_position_value = equity * (max_position_pct / Decimal("100"))
    final_position_value = min(position_value, max_position_value)
    quantity_pct = final_position_value / equity if equity > 0 else Decimal("0")
    quantity_pct = max(Decimal("0"), min(quantity_pct, Decimal("1.0")))

    return PositionSizingResult(
        quantity_pct=quantity_pct,
        stop_loss_price=stop_loss_price.quantize(Decimal("0.00000001")),
        take_profit_price=take_profit_price.quantize(Decimal("0.00000001")),
        risk_amount=adjusted_risk.quantize(Decimal("0.00000001")),
        position_value=final_position_value.quantize(Decimal("0.00000001")),
        stop_distance=stop_distance.quantize(Decimal("0.00000001")),
        stop_distance_pct=stop_distance_pct.quantize(Decimal("0.00000001")),
        confidence_multiplier=confidence_multiplier,
        streak_multiplier=streak_multiplier,
        entry_atr=atr.quantize(Decimal("0.00000001")),
    )
