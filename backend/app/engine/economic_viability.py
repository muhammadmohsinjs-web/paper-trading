"""Economic viability checks for pre-trade filtering."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.engine.fee_model import SPOT_FEE_RATE
from app.engine.reason_codes import (
    NET_REWARD_NON_POSITIVE,
    NET_REWARD_TOO_SMALL,
    NET_RR_TOO_LOW,
    REWARD_TO_COST_TOO_LOW,
    TP_BELOW_COST_BUFFER,
)
from app.engine.trade_quality import resolve_trade_quality_thresholds
from app.engine.slippage import estimate_slippage_rate


@dataclass(frozen=True)
class EconomicViabilityResult:
    passed: bool
    reason_codes: list[str]
    reason_text: str
    gross_reward_pct: float
    gross_risk_pct: float
    total_round_trip_cost_pct: float
    net_reward_pct: float
    net_risk_pct: float
    net_rr: float
    reward_to_cost_ratio: float
    entry_slippage_rate_pct: float
    exit_slippage_rate_pct: float
    min_gross_reward_cost_multiple: float
    min_net_reward_pct: float
    min_net_rr: float
    min_reward_to_cost_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason_codes": list(self.reason_codes),
            "reason_text": self.reason_text,
            "gross_reward_pct": self.gross_reward_pct,
            "gross_risk_pct": self.gross_risk_pct,
            "total_round_trip_cost_pct": self.total_round_trip_cost_pct,
            "net_reward_pct": self.net_reward_pct,
            "net_risk_pct": self.net_risk_pct,
            "net_rr": self.net_rr,
            "reward_to_cost_ratio": self.reward_to_cost_ratio,
            "entry_slippage_rate_pct": self.entry_slippage_rate_pct,
            "exit_slippage_rate_pct": self.exit_slippage_rate_pct,
            "min_gross_reward_cost_multiple": self.min_gross_reward_cost_multiple,
            "min_net_reward_pct": self.min_net_reward_pct,
            "min_net_rr": self.min_net_rr,
            "min_reward_to_cost_ratio": self.min_reward_to_cost_ratio,
        }


def evaluate_economic_viability(
    *,
    entry_price: Decimal,
    stop_loss_price: Decimal,
    take_profit_price: Decimal,
    notional: Decimal | None = None,
    fee_rate: Decimal = SPOT_FEE_RATE,
    entry_slippage_rate: Decimal | None = None,
    exit_slippage_rate: Decimal | None = None,
    config: dict[str, Any] | None = None,
) -> EconomicViabilityResult:
    thresholds = resolve_trade_quality_thresholds(config)
    trade_notional = notional or Decimal("1000")
    entry_slippage = entry_slippage_rate if entry_slippage_rate is not None else estimate_slippage_rate(trade_notional)
    exit_slippage = exit_slippage_rate if exit_slippage_rate is not None else estimate_slippage_rate(trade_notional)

    if entry_price <= 0:
        return EconomicViabilityResult(
            passed=False,
            reason_codes=[NET_REWARD_NON_POSITIVE],
            reason_text="Invalid entry price",
            gross_reward_pct=0.0,
            gross_risk_pct=0.0,
            total_round_trip_cost_pct=0.0,
            net_reward_pct=0.0,
            net_risk_pct=0.0,
            net_rr=0.0,
            reward_to_cost_ratio=0.0,
            entry_slippage_rate_pct=0.0,
            exit_slippage_rate_pct=0.0,
            min_gross_reward_cost_multiple=thresholds.min_gross_reward_cost_multiple,
            min_net_reward_pct=thresholds.min_net_reward_pct,
            min_net_rr=thresholds.min_net_rr,
            min_reward_to_cost_ratio=thresholds.min_reward_to_cost_ratio,
        )

    gross_reward_pct = float((take_profit_price - entry_price) / entry_price * Decimal("100"))
    gross_risk_pct = float((entry_price - stop_loss_price) / entry_price * Decimal("100"))
    total_round_trip_cost_pct = float((fee_rate * Decimal("2") + entry_slippage + exit_slippage) * Decimal("100"))
    net_reward_pct = gross_reward_pct - total_round_trip_cost_pct
    net_risk_pct = gross_risk_pct + total_round_trip_cost_pct
    net_rr = (net_reward_pct / net_risk_pct) if net_risk_pct > 0 else 0.0
    reward_to_cost_ratio = gross_reward_pct / total_round_trip_cost_pct if total_round_trip_cost_pct > 0 else 0.0

    reason_codes: list[str] = []
    if net_reward_pct <= 0:
        reason_codes.append(NET_REWARD_NON_POSITIVE)
    if gross_reward_pct < total_round_trip_cost_pct * thresholds.min_gross_reward_cost_multiple:
        reason_codes.append(TP_BELOW_COST_BUFFER)
    if net_reward_pct < thresholds.min_net_reward_pct:
        reason_codes.append(NET_REWARD_TOO_SMALL)
    if net_rr < thresholds.min_net_rr:
        reason_codes.append(NET_RR_TOO_LOW)
    if reward_to_cost_ratio < thresholds.min_reward_to_cost_ratio:
        reason_codes.append(REWARD_TO_COST_TOO_LOW)

    reason_text = "; ".join(reason_codes) if reason_codes else "Setup passed economic viability checks"
    return EconomicViabilityResult(
        passed=not reason_codes,
        reason_codes=reason_codes,
        reason_text=reason_text,
        gross_reward_pct=round(gross_reward_pct, 4),
        gross_risk_pct=round(gross_risk_pct, 4),
        total_round_trip_cost_pct=round(total_round_trip_cost_pct, 4),
        net_reward_pct=round(net_reward_pct, 4),
        net_risk_pct=round(net_risk_pct, 4),
        net_rr=round(net_rr, 4),
        reward_to_cost_ratio=round(reward_to_cost_ratio, 4),
        entry_slippage_rate_pct=round(float(entry_slippage * Decimal("100")), 4),
        exit_slippage_rate_pct=round(float(exit_slippage * Decimal("100")), 4),
        min_gross_reward_cost_multiple=thresholds.min_gross_reward_cost_multiple,
        min_net_reward_pct=thresholds.min_net_reward_pct,
        min_net_rr=thresholds.min_net_rr,
        min_reward_to_cost_ratio=thresholds.min_reward_to_cost_ratio,
    )
