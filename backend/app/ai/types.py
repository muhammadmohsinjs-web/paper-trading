from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class AITradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class AIStrategyProfile(str, Enum):
    RSI_MA = "A"
    PRICE_ACTION = "B"
    VOLUME_MACD = "C"
    CHART_PATTERNS = "D"

    @classmethod
    def from_value(cls, value: str) -> "AIStrategyProfile":
        normalized = value.strip().lower()
        aliases = {
            "a": cls.RSI_MA,
            "rsi_ma": cls.RSI_MA,
            "rsi+ma": cls.RSI_MA,
            "rsi_ma_crossover": cls.RSI_MA,
            "b": cls.PRICE_ACTION,
            "price_action": cls.PRICE_ACTION,
            "price-action": cls.PRICE_ACTION,
            "c": cls.VOLUME_MACD,
            "volume_macd": cls.VOLUME_MACD,
            "volume-macd": cls.VOLUME_MACD,
            "d": cls.CHART_PATTERNS,
            "chart_patterns": cls.CHART_PATTERNS,
            "chart-patterns": cls.CHART_PATTERNS,
        }
        profile = aliases.get(normalized)
        if profile is None:
            raise ValueError(f"Unknown AI strategy profile: {value}")
        return profile


@dataclass
class MarketSnapshot:
    symbol: str
    interval: str
    current_price: Decimal
    closes: list[Decimal] = field(default_factory=list)
    highs: list[Decimal] = field(default_factory=list)
    lows: list[Decimal] = field(default_factory=list)
    volumes: list[Decimal] = field(default_factory=list)
    indicators: dict[str, Any] = field(default_factory=dict)
    has_position: bool = False
    position_quantity: Decimal | None = None
    entry_price: Decimal | None = None
    available_usdt: Decimal | None = None
    initial_balance_usdt: Decimal | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class TradeDecision:
    action: AITradeAction
    symbol: str
    quantity_pct: Decimal = Decimal("0")
    reason: str = ""
    confidence: float | None = None
    strategy_profile: AIStrategyProfile | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)
    repaired: bool = False


@dataclass
class AIUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class AIAnalysisResult:
    decision: TradeDecision
    raw_text: str
    usage: AIUsage = field(default_factory=AIUsage)
    model: str | None = None
    stop_reason: str | None = None
    repaired: bool = False
    fallback: bool = False

