"""Market regime types and data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MarketRegime(str, Enum):
    """Detected market regime classification."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    CRASH = "crash"


@dataclass(frozen=True)
class RegimeResult:
    """Output of the regime classifier."""

    regime: MarketRegime
    confidence: float  # 0.0 to 1.0
    metrics: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""

    def is_trending(self) -> bool:
        return self.regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN)

    def is_dangerous(self) -> bool:
        return self.regime in (MarketRegime.HIGH_VOLATILITY, MarketRegime.CRASH)
