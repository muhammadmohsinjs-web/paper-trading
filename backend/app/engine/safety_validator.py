"""Deterministic trade safety validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.engine.economic_viability import EconomicViabilityResult
from app.engine.tradability import MovementQuality, TradabilityResult


@dataclass(frozen=True)
class SafetyVerdict:
    status: str
    approved: bool
    reason_code: str | None
    reason_text: str
    fatal_flags: list[str]
    evidence: dict[str, Any]
    usage: Any | None = None
    raw_response: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "approved": self.approved,
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "fatal_flags": list(self.fatal_flags),
            "evidence": dict(self.evidence),
        }


def evaluate_local_trade_safety(
    *,
    tradability: TradabilityResult,
    movement_quality: MovementQuality,
    economic_viability: EconomicViabilityResult,
) -> SafetyVerdict:
    fatal_flags: list[str] = []
    evidence = {
        "tradability": tradability.to_dict(),
        "movement_quality": movement_quality.to_dict(),
        "economic_viability": economic_viability.to_dict(),
    }

    tradability_codes = set(tradability.reason_codes)
    economic_codes = set(economic_viability.reason_codes)
    movement_code = movement_quality.reason_code

    if "DENYLIST_STABLE_BASE" in tradability_codes or "NEAR_PEG_PROFILE" in tradability_codes:
        fatal_flags.append("NEAR_PEG_MARKET")
    if "ATR_PCT_TOO_LOW" in tradability_codes:
        fatal_flags.append("ULTRA_LOW_ATR")
    if economic_codes:
        fatal_flags.append("FEE_NEGATIVE_SETUP")
    if movement_code in {"SETUP_NO_ABSOLUTE_EXPANSION", "SETUP_RANGE_TOO_SMALL"}:
        fatal_flags.append("NO_EXPANSION_PATH")
    if not movement_quality.passed or "MARKET_QUALITY_TOO_LOW" in tradability_codes:
        fatal_flags.append("LOW_QUALITY_STRUCTURE")

    fatal_flags = list(dict.fromkeys(fatal_flags))
    approved = not fatal_flags
    reason_code = fatal_flags[0] if fatal_flags else None
    reason_text = reason_code or "Local safety checks passed"
    return SafetyVerdict(
        status="approved" if approved else "rejected",
        approved=approved,
        reason_code=reason_code,
        reason_text=reason_text,
        fatal_flags=fatal_flags,
        evidence=evidence,
    )
