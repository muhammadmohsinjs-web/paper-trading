"""Strategy selector — chooses the best strategy based on regime and performance history."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.regime.types import DetailedRegime, MarketRegime

logger = logging.getLogger(__name__)

# Hardcoded baseline affinity: how well each strategy performs in each regime.
# Values 0.0 to 1.0. Based on theoretical alignment of strategy type to market condition.
REGIME_AFFINITY: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.TRENDING_UP: {
        "sma_crossover": 0.85,
        "macd_momentum": 0.90,
        "rsi_mean_reversion": 0.30,
        "bollinger_bounce": 0.40,
        "hybrid_composite": 0.75,
        "hybrid_ai_composite": 0.75,
    },
    MarketRegime.TRENDING_DOWN: {
        "sma_crossover": 0.70,
        "macd_momentum": 0.80,
        "rsi_mean_reversion": 0.50,
        "bollinger_bounce": 0.45,
        "hybrid_composite": 0.70,
        "hybrid_ai_composite": 0.70,
    },
    MarketRegime.RANGING: {
        "sma_crossover": 0.20,
        "macd_momentum": 0.30,
        "rsi_mean_reversion": 0.90,
        "bollinger_bounce": 0.85,
        "hybrid_composite": 0.65,
        "hybrid_ai_composite": 0.65,
    },
    MarketRegime.HIGH_VOLATILITY: {
        "sma_crossover": 0.15,
        "macd_momentum": 0.25,
        "rsi_mean_reversion": 0.40,
        "bollinger_bounce": 0.60,
        "hybrid_composite": 0.50,
        "hybrid_ai_composite": 0.50,
    },
    MarketRegime.CRASH: {
        "sma_crossover": 0.0,
        "macd_momentum": 0.0,
        "rsi_mean_reversion": 0.10,
        "bollinger_bounce": 0.10,
        "hybrid_composite": 0.05,
        "hybrid_ai_composite": 0.05,
    },
}

# Detailed regime affinity — higher resolution than coarse REGIME_AFFINITY.
# Strategy scorer prefers this when detailed_regime is available.
_S = {
    "sma_crossover", "macd_momentum", "rsi_mean_reversion",
    "bollinger_bounce", "hybrid_composite", "hybrid_ai_composite",
}

DETAILED_REGIME_AFFINITY: dict[DetailedRegime, dict[str, float]] = {
    DetailedRegime.CLEAN_TREND_UP: {
        "sma_crossover": 0.90, "macd_momentum": 0.95,
        "rsi_mean_reversion": 0.20, "bollinger_bounce": 0.30,
        "hybrid_composite": 0.80, "hybrid_ai_composite": 0.80,
    },
    DetailedRegime.CLEAN_TREND_DOWN: {
        "sma_crossover": 0.75, "macd_momentum": 0.85,
        "rsi_mean_reversion": 0.40, "bollinger_bounce": 0.35,
        "hybrid_composite": 0.70, "hybrid_ai_composite": 0.70,
    },
    DetailedRegime.EXHAUSTED_TREND_UP: {
        "sma_crossover": 0.40, "macd_momentum": 0.35,
        "rsi_mean_reversion": 0.70, "bollinger_bounce": 0.65,
        "hybrid_composite": 0.55, "hybrid_ai_composite": 0.55,
    },
    DetailedRegime.EXHAUSTED_TREND_DOWN: {
        "sma_crossover": 0.30, "macd_momentum": 0.30,
        "rsi_mean_reversion": 0.75, "bollinger_bounce": 0.60,
        "hybrid_composite": 0.50, "hybrid_ai_composite": 0.50,
    },
    DetailedRegime.VOLATILE_TREND_UP: {
        "sma_crossover": 0.55, "macd_momentum": 0.70,
        "rsi_mean_reversion": 0.35, "bollinger_bounce": 0.50,
        "hybrid_composite": 0.60, "hybrid_ai_composite": 0.60,
    },
    DetailedRegime.VOLATILE_TREND_DOWN: {
        "sma_crossover": 0.40, "macd_momentum": 0.55,
        "rsi_mean_reversion": 0.45, "bollinger_bounce": 0.50,
        "hybrid_composite": 0.50, "hybrid_ai_composite": 0.50,
    },
    DetailedRegime.CLEAN_RANGE: {
        "sma_crossover": 0.20, "macd_momentum": 0.25,
        "rsi_mean_reversion": 0.95, "bollinger_bounce": 0.90,
        "hybrid_composite": 0.70, "hybrid_ai_composite": 0.70,
    },
    DetailedRegime.CHAOTIC_RANGE: {
        "sma_crossover": 0.10, "macd_momentum": 0.15,
        "rsi_mean_reversion": 0.50, "bollinger_bounce": 0.55,
        "hybrid_composite": 0.40, "hybrid_ai_composite": 0.40,
    },
    DetailedRegime.BREAKOUT_EXPANSION: {
        "sma_crossover": 0.70, "macd_momentum": 0.90,
        "rsi_mean_reversion": 0.15, "bollinger_bounce": 0.25,
        "hybrid_composite": 0.75, "hybrid_ai_composite": 0.75,
    },
    DetailedRegime.POST_SPIKE_INSTABILITY: {
        "sma_crossover": 0.10, "macd_momentum": 0.15,
        "rsi_mean_reversion": 0.45, "bollinger_bounce": 0.40,
        "hybrid_composite": 0.30, "hybrid_ai_composite": 0.30,
    },
    DetailedRegime.CRASH: {
        "sma_crossover": 0.0, "macd_momentum": 0.0,
        "rsi_mean_reversion": 0.10, "bollinger_bounce": 0.10,
        "hybrid_composite": 0.05, "hybrid_ai_composite": 0.05,
    },
}

# Minimum trades required before we trust actual performance data
MIN_TRADES_FOR_PERFORMANCE = 20


@dataclass
class StrategyScore:
    """Computed selection score for a strategy."""

    strategy_type: str
    score: float
    regime_affinity: float
    performance_sharpe: float
    recent_win_rate: float
    reasoning: str


@dataclass
class PerformanceRecord:
    """Rolling performance data for a strategy in a specific regime."""

    strategy_type: str
    regime: MarketRegime
    total_trades: int = 0
    winning_trades: int = 0
    sharpe_ratio: float = 0.0
    total_pnl: float = 0.0


class StrategySelector:
    """Selects the best strategy for current market conditions.

    Combines hardcoded regime affinity with actual rolling performance data.
    """

    def __init__(self) -> None:
        self._performance_cache: dict[tuple[str, MarketRegime], PerformanceRecord] = {}

    def update_performance(
        self,
        strategy_type: str,
        regime: MarketRegime,
        trade_pnl: float,
        sharpe_estimate: float = 0.0,
    ) -> None:
        """Update rolling performance for a strategy in a regime.

        Called after each trade to build historical performance data.
        """
        key = (strategy_type, regime)
        record = self._performance_cache.get(key)
        if record is None:
            record = PerformanceRecord(strategy_type=strategy_type, regime=regime)
            self._performance_cache[key] = record

        record.total_trades += 1
        if trade_pnl > 0:
            record.winning_trades += 1
        record.total_pnl += trade_pnl
        record.sharpe_ratio = sharpe_estimate

    def select(
        self,
        regime: MarketRegime,
        available_strategies: list[str] | None = None,
    ) -> list[StrategyScore]:
        """Rank strategies for the current regime.

        Returns a sorted list of StrategyScore (best first).
        """
        strategies = available_strategies or list(
            REGIME_AFFINITY.get(regime, {}).keys()
        )

        scores: list[StrategyScore] = []
        for strategy_type in strategies:
            score = self._compute_score(strategy_type, regime)
            scores.append(score)

        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    def get_best(
        self,
        regime: MarketRegime,
        available_strategies: list[str] | None = None,
    ) -> StrategyScore | None:
        """Get the single best strategy for the current regime."""
        ranked = self.select(regime, available_strategies)
        return ranked[0] if ranked else None

    def get_regime_recommendation(
        self,
        regime: MarketRegime,
    ) -> dict[str, Any]:
        """Get regime-specific trading recommendations."""
        ranked = self.select(regime)
        recommendations: dict[str, Any] = {
            "regime": regime.value,
            "action_mode": "normal",
            "position_size_multiplier": 1.0,
            "ranking": [
                {
                    "strategy": s.strategy_type,
                    "score": round(s.score, 3),
                    "regime_affinity": round(s.regime_affinity, 3),
                }
                for s in ranked
            ],
        }

        if regime == MarketRegime.CRASH:
            recommendations["action_mode"] = "exit_only"
            recommendations["position_size_multiplier"] = 0.0
            recommendations["warning"] = "CRASH detected — no new entries allowed"
        elif regime == MarketRegime.HIGH_VOLATILITY:
            recommendations["action_mode"] = "reduced"
            recommendations["position_size_multiplier"] = 0.5
            recommendations["warning"] = "High volatility — position sizes reduced 50%"

        return recommendations

    def _compute_score(
        self,
        strategy_type: str,
        regime: MarketRegime,
    ) -> StrategyScore:
        """Compute selection score for a strategy in a regime."""
        # Component 1: Regime affinity (40% weight)
        affinity_map = REGIME_AFFINITY.get(regime, {})
        regime_affinity = affinity_map.get(strategy_type, 0.5)

        # Component 2: Rolling performance (30% weight)
        perf = self._performance_cache.get((strategy_type, regime))
        if perf and perf.total_trades >= MIN_TRADES_FOR_PERFORMANCE:
            performance_sharpe = max(min(perf.sharpe_ratio, 3.0), -3.0) / 3.0  # normalize to [0, 1]
            performance_sharpe = (performance_sharpe + 1) / 2  # shift to [0, 1]
        else:
            performance_sharpe = 0.5  # neutral when no data

        # Component 3: Recent win rate (20% weight)
        if perf and perf.total_trades >= 5:
            recent_win_rate = perf.winning_trades / perf.total_trades
        else:
            recent_win_rate = 0.5  # neutral

        # Component 4: Recency (10% weight) — strategies that traded recently get a small boost
        recency_score = 0.5  # placeholder until we track recency

        # Weighted combination
        score = (
            regime_affinity * 0.4
            + performance_sharpe * 0.3
            + recent_win_rate * 0.2
            + recency_score * 0.1
        )

        reasoning = (
            f"affinity={regime_affinity:.2f} "
            f"sharpe_norm={performance_sharpe:.2f} "
            f"win_rate={recent_win_rate:.2f} "
            f"trades={perf.total_trades if perf else 0}"
        )

        return StrategyScore(
            strategy_type=strategy_type,
            score=score,
            regime_affinity=regime_affinity,
            performance_sharpe=performance_sharpe,
            recent_win_rate=recent_win_rate,
            reasoning=reasoning,
        )
