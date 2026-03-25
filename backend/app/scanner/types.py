"""Scanner data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RankedSetup:
    """A scored trading opportunity detected by the scanner."""

    symbol: str
    score: float
    setup_type: str  # e.g., "rsi_oversold", "bb_squeeze", "volume_breakout"
    signal: str  # "BUY" or "SELL"
    regime: str
    recommended_strategy: str
    reason: str
    indicators: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Complete result of an opportunity scan."""

    scanned_at: str  # ISO timestamp
    symbols_scanned: int
    regime: str
    opportunities: list[RankedSetup] = field(default_factory=list)
