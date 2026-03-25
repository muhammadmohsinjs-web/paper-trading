"""Abstract base for trading strategy decision-making."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.engine.executor import TradeSignal


@dataclass
class StrategyContext:
    """Extended context for strategies that need more than basic indicators.

    Rule-based strategies (SMA, RSI, MACD, Bollinger) ignore this.
    The HybridCompositeStrategy and future advanced strategies use it.
    """

    # Market data
    symbol: str = "BTCUSDT"
    interval: str = "1h"
    market_price: Decimal = Decimal("0")
    closes: list[float] = field(default_factory=list)
    highs: list[float] = field(default_factory=list)
    lows: list[float] = field(default_factory=list)
    volumes: list[float] = field(default_factory=list)

    # Position state
    has_position: bool = False
    position: Any = None  # Position model instance or None

    # Wallet state
    wallet: Any = None  # Wallet model instance
    equity: Decimal = Decimal("0")

    # Strategy metadata
    strategy_id: str = ""
    strategy_name: str = ""
    strategy_type: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    regime: str = ""

    # AI configuration (resolved)
    ai_config: dict[str, Any] = field(default_factory=dict)

    # Risk parameters from strategy model
    risk_per_trade_pct: Decimal = Decimal("2.0")
    max_position_size_pct: Decimal = Decimal("30.0")
    stop_loss_pct: Decimal = Decimal("3.0")
    consecutive_losses: int = 0

    # Force flag (manual execution)
    force: bool = False


def latest_scalar(value: Any) -> Any:
    """Return the latest element for list-like indicator values."""
    if isinstance(value, (list, tuple)):
        return value[-1] if value else None
    return value


class BaseStrategy(ABC):
    """Interface that all strategies must implement."""

    @abstractmethod
    def decide(
        self,
        indicators: dict,
        has_position: bool,
        available_usdt: Decimal,
    ) -> TradeSignal | None:
        """Return a TradeSignal or None (HOLD)."""
        ...

    def decide_with_context(
        self,
        indicators: dict,
        has_position: bool,
        available_usdt: Decimal,
        context: StrategyContext | None = None,
    ) -> TradeSignal | None:
        """Extended decision method with full context.

        Default implementation delegates to decide() for backward compatibility.
        Override in strategies that need the extended context (e.g. HybridComposite).
        """
        return self.decide(indicators, has_position, available_usdt)
