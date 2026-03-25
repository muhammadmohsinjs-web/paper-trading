"""Strategy registry — maps strategy names to their implementations."""

from __future__ import annotations

from app.strategies.base import BaseStrategy
from app.strategies.bollinger_bounce import BollingerBounceStrategy
from app.strategies.hybrid_composite import HybridCompositeStrategy
from app.strategies.macd_momentum import MACDMomentumStrategy
from app.strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from app.strategies.sma_crossover import SMACrossoverStrategy

_REGISTRY: dict[str, type[BaseStrategy]] = {
    "sma_crossover": SMACrossoverStrategy,
    "rsi_mean_reversion": RSIMeanReversionStrategy,
    "macd_momentum": MACDMomentumStrategy,
    "bollinger_bounce": BollingerBounceStrategy,
    "hybrid_composite": HybridCompositeStrategy,
}


def get_strategy_class(name: str) -> type[BaseStrategy]:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(_REGISTRY.keys())}")
    return cls


def list_strategies() -> list[str]:
    return list(_REGISTRY.keys())
