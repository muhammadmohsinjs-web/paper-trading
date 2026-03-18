"""Abstract base for trading strategy decision-making."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from app.engine.executor import TradeSignal


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
