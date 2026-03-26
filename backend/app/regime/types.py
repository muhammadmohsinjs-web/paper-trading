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


# Favorable transitions for long entries
_FAVORABLE_TRANSITIONS = {
    (MarketRegime.RANGING, MarketRegime.TRENDING_UP),
    (MarketRegime.TRENDING_DOWN, MarketRegime.RANGING),
    (MarketRegime.CRASH, MarketRegime.RANGING),
    (MarketRegime.HIGH_VOLATILITY, MarketRegime.TRENDING_UP),
}

# Dangerous transitions requiring immediate attention
_DANGEROUS_TRANSITIONS = {
    (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN),
    (MarketRegime.TRENDING_UP, MarketRegime.CRASH),
    (MarketRegime.RANGING, MarketRegime.CRASH),
    (MarketRegime.RANGING, MarketRegime.TRENDING_DOWN),
}


@dataclass(frozen=True)
class RegimeTransition:
    """Detected transition between market regimes."""

    from_regime: MarketRegime
    to_regime: MarketRegime
    is_favorable: bool  # True if transitioning to a better regime for longs
    is_dangerous: bool  # True if immediate exit may be needed
    urgency: float  # 0.0 to 1.0 — how quickly to react

    @staticmethod
    def detect(
        previous: MarketRegime | None,
        current: MarketRegime,
    ) -> RegimeTransition | None:
        """Detect a regime transition. Returns None if no change."""
        if previous is None or previous == current:
            return None

        pair = (previous, current)
        is_fav = pair in _FAVORABLE_TRANSITIONS
        is_dang = pair in _DANGEROUS_TRANSITIONS

        # Urgency: crash transitions are most urgent
        if current == MarketRegime.CRASH:
            urgency = 1.0
        elif is_dang:
            urgency = 0.8
        elif is_fav:
            urgency = 0.5
        else:
            urgency = 0.3

        return RegimeTransition(
            from_regime=previous,
            to_regime=current,
            is_favorable=is_fav,
            is_dangerous=is_dang,
            urgency=urgency,
        )
