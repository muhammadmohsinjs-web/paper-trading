"""Scanner data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActivityScore:
    """Market quality score for a symbol — used by dynamic universe selection."""

    symbol: str
    activity_score: float  # Composite score [0.0, 1.0]
    volume_surge: float  # Volume vs 7-day average
    volatility_quality: float  # ATR/price in ideal range
    trend_clarity: float  # ADX-based trend quality
    liquidity_depth: float  # 24h USDT volume tier
    relative_strength: float  # Performance vs BTC
    volume_24h_usdt: float  # Raw 24h quote volume
    tradability_passed: bool = True
    reason_codes: list[str] = field(default_factory=list)
    reason_text: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    is_new_entrant: bool = False  # Newly entered Active Universe


@dataclass
class CandidateInfo:
    """Minimal ticker data for a coin in the candidate pool."""

    symbol: str
    price: float
    volume_24h_usdt: float  # 24h quote volume
    price_change_pct_24h: float  # 24h price change %
    liquidity_archetype: str = ""
    threshold_volume_24h_usdt: float = 0.0
    volume_1h_usdt: float = 0.0
    threshold_volume_1h_usdt: float = 0.0
    tradability_passed: bool = True
    reason_codes: list[str] = field(default_factory=list)
    reason_text: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    market_quality_score: float = 0.0


@dataclass
class UniverseSnapshot:
    """Point-in-time snapshot of the dynamic universe state."""

    timestamp: str  # ISO format
    candidate_pool_size: int
    active_universe_size: int
    active_symbols: list[str] = field(default_factory=list)
    promoted: list[str] = field(default_factory=list)  # Newly entered
    demoted: list[str] = field(default_factory=list)  # Removed
    scores: list[ActivityScore] = field(default_factory=list)
    candidate_evaluations: list[CandidateInfo] = field(default_factory=list)
    total_usdt_pairs: int = 0
    tradability_failed_count: int = 0


@dataclass
class SetupAuditNote:
    symbol: str
    setup_type: str
    status: str
    reason_code: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    reason_text: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


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
    reason_code: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    reason_text: str = ""
    movement_quality: dict[str, Any] = field(default_factory=dict)
    liquidity_usdt: float = 0.0
    market_quality_score: float = 0.0
    reward_to_cost_ratio: float = 0.0
    volatility_quality_score: float = 0.5
    # Family-aware metadata (additive)
    family: str = ""
    entry_eligible: bool = True
    symbol_quality_score: float = 0.0
    execution_quality_score: float = 0.0
    room_to_move_score: float = 0.0
    conflict_penalty: float = 0.0
    freshness_score: float = 1.0
    detailed_regime: str = ""


@dataclass
class RankedSymbol:
    """A ranked symbol candidate selected from the scanner universe."""

    symbol: str
    score: float
    regime: str
    setup_type: str
    recommended_strategy: str
    reason: str
    liquidity_usdt: float
    indicators: dict[str, Any] = field(default_factory=dict)
    reason_code: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    reason_text: str = ""
    movement_quality: dict[str, Any] = field(default_factory=dict)
    # Family-aware metadata (additive)
    family: str = ""
    entry_eligible: bool = True
    net_quality_score: float = 0.0
    contradiction_penalty: float = 0.0
    exhaustion_penalty: float = 0.0
    detailed_regime: str = ""


@dataclass
class ScanResult:
    """Complete result of an opportunity scan."""

    scanned_at: str  # ISO timestamp
    symbols_scanned: int
    regime: str
    opportunities: list[RankedSetup] = field(default_factory=list)
