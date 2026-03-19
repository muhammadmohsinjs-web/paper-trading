"""Exit evaluation for hybrid strategy positions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ExitDecision:
    action: str
    quantity_pct: Decimal
    reason: str
    exit_type: str | None = None
    updated_trailing_stop_price: Decimal | None = None
    consume_take_profit: bool = False


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def calculate_trailing_stop(
    *,
    entry_price: Decimal,
    current_price: Decimal,
    entry_atr: Decimal | None,
    atr_trail_multiplier: Decimal,
    current_trailing_stop: Decimal | None,
) -> Decimal | None:
    if entry_atr is None or entry_atr <= 0:
        return current_trailing_stop
    if current_price - entry_price < entry_atr:
        return current_trailing_stop

    candidate = current_price - (entry_atr * atr_trail_multiplier)
    if current_trailing_stop is None or candidate > current_trailing_stop:
        return candidate.quantize(Decimal("0.00000001"))
    return current_trailing_stop


def evaluate_exit(
    *,
    position: Any,
    current_price: Decimal,
    composite_score: float | None = None,
    config: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> ExitDecision:
    cfg = config or {}
    now_aware = now or datetime.now(timezone.utc)
    entry_price = _to_decimal(position.entry_price) or Decimal("0")
    entry_atr = _to_decimal(getattr(position, "entry_atr", None))
    stop_loss_price = _to_decimal(getattr(position, "stop_loss_price", None))
    take_profit_price = _to_decimal(getattr(position, "take_profit_price", None))
    trailing_stop_price = _to_decimal(getattr(position, "trailing_stop_price", None))
    atr_trail_multiplier = Decimal(str(cfg.get("atr_trail_multiplier", 1.5)))
    time_stop_hours = float(cfg.get("time_stop_hours", 48))
    reversal_threshold = float(cfg.get("signal_reversal_threshold", -0.4))

    if stop_loss_price is not None and current_price <= stop_loss_price:
        return ExitDecision(
            action="SELL",
            quantity_pct=Decimal("1.0"),
            reason=f"Stop-loss triggered at {current_price}",
            exit_type="stop_loss",
        )

    trailing_candidate = calculate_trailing_stop(
        entry_price=entry_price,
        current_price=current_price,
        entry_atr=entry_atr,
        atr_trail_multiplier=atr_trail_multiplier,
        current_trailing_stop=trailing_stop_price,
    )

    if take_profit_price is not None and current_price >= take_profit_price:
        return ExitDecision(
            action="SELL",
            quantity_pct=Decimal("0.7"),
            reason=f"Take-profit triggered at {current_price}",
            exit_type="take_profit",
            updated_trailing_stop_price=trailing_candidate,
            consume_take_profit=True,
        )

    if trailing_candidate is not None and current_price <= trailing_candidate:
        return ExitDecision(
            action="SELL",
            quantity_pct=Decimal("1.0"),
            reason=f"Trailing stop triggered at {current_price}",
            exit_type="trailing_stop",
            updated_trailing_stop_price=trailing_candidate,
        )

    opened_at = getattr(position, "opened_at", None)
    if opened_at is not None and opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=timezone.utc)
    hours_open = (now_aware - opened_at).total_seconds() / 3600 if opened_at else 0.0
    if entry_atr is not None and hours_open > time_stop_hours and abs(current_price - entry_price) < entry_atr:
        return ExitDecision(
            action="SELL",
            quantity_pct=Decimal("1.0"),
            reason=f"Time stop triggered after {hours_open:.1f}h",
            exit_type="time_stop",
        )

    if composite_score is not None and composite_score <= reversal_threshold:
        return ExitDecision(
            action="SELL",
            quantity_pct=Decimal("1.0"),
            reason=f"Signal reversal triggered at score {composite_score:.3f}",
            exit_type="signal_reversal",
            updated_trailing_stop_price=trailing_candidate,
        )

    return ExitDecision(
        action="HOLD",
        quantity_pct=Decimal("0"),
        reason="No exit condition met",
        updated_trailing_stop_price=trailing_candidate,
    )
