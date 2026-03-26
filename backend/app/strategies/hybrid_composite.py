"""Hybrid Composite Strategy — multi-indicator weighted system.

Extracted from engine/trading_loop.py for modularity. This strategy:
1. Computes a composite score from RSI, MACD, SMA, EMA, Volume votes
2. Produces deterministic entry candidates for the live validator pipeline
3. Uses ATR-based position sizing with confidence tiers
4. Manages exits via stop-loss, take-profit, trailing stop, time stop, signal reversal
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.engine.composite_scorer import (
    compute_composite_score,
    CompositeScoreResult,
)
from app.engine.executor import TradeSignal
from app.engine.exit_manager import ExitDecision, evaluate_exit
from app.engine.position_sizer import calculate_position_size, PositionSizingResult
from app.models.enums import TradeSide
from app.strategies.base import BaseStrategy, StrategyContext

logger = logging.getLogger(__name__)


@dataclass
class HybridDecision:
    """Result of the hybrid composite decision process."""

    signal: TradeSignal | None = None
    composite_result: CompositeScoreResult | None = None
    exit_decision: ExitDecision | None = None
    raw_confidence: float | None = None
    status: str = "hold"
    reason: str = ""
    decision_source: str = "hybrid_entry"
    skip_reason: str | None = None

class HybridCompositeStrategy(BaseStrategy):
    """Weighted multi-indicator composite strategy."""

    def decide(
        self,
        indicators: dict,
        has_position: bool,
        available_usdt: Decimal,
    ) -> TradeSignal | None:
        """Basic decide used outside the live validator pipeline."""
        result = compute_composite_score(indicators, config=None)
        if not has_position and result.signal == "BUY":
            return TradeSignal(
                action=TradeSide.BUY,
                symbol=str(indicators.get("symbol") or "BTCUSDT"),
                quantity_pct=Decimal("0.3"),
                reason=(
                    f"Hybrid composite BUY score={result.composite_score:.3f} "
                    f"confidence={result.confidence:.3f}"
                ),
            )
        if has_position and result.signal == "SELL":
            return TradeSignal(
                action=TradeSide.SELL,
                symbol=str(indicators.get("symbol") or "BTCUSDT"),
                quantity_pct=Decimal("1.0"),
                reason=(
                    f"Hybrid composite SELL score={result.composite_score:.3f} "
                    f"confidence={result.confidence:.3f}"
                ),
            )
        return None

    def decide_with_context(
        self,
        indicators: dict,
        has_position: bool,
        available_usdt: Decimal,
        context: StrategyContext | None = None,
    ) -> TradeSignal | None:
        """Synchronous wrapper for deterministic hybrid checks."""
        if context is None:
            return self.decide(indicators, has_position, available_usdt)
        result = compute_composite_score(
            indicators,
            config=context.config,
            regime=context.regime,
            market_quality_score=context.market_quality_score,
            movement_quality_score=context.movement_quality_score,
        )
        if not has_position and result.signal == "BUY":
            return TradeSignal(
                action=TradeSide.BUY,
                symbol=context.symbol,
                quantity_pct=Decimal("0.3"),
                reason=(
                    f"Hybrid composite BUY score={result.composite_score:.3f} "
                    f"confidence={result.confidence:.3f}"
                ),
            )
        return None

    async def decide_hybrid_async(
        self,
        indicators: dict,
        context: StrategyContext,
    ) -> HybridDecision:
        """Build a deterministic hybrid candidate for the live pipeline."""
        config = context.config
        position = context.position
        market_price = context.market_price

        composite_result = compute_composite_score(
            indicators,
            config=config,
            regime=context.regime,
            market_quality_score=context.market_quality_score,
            movement_quality_score=context.movement_quality_score,
        )

        # Step 4: Exit evaluation (if has position)
        if position is not None:
            exit_result = self._evaluate_exit(
                position, market_price, composite_result, config,
                regime=context.regime,
            )
            exit_result.composite_result = composite_result
            return exit_result

        if composite_result.direction != "BUY":
            return HybridDecision(
                composite_result=composite_result,
                raw_confidence=composite_result.confidence,
                status="hold",
                reason="Hybrid composite gate not met",
                decision_source="hybrid_entry",
            )

        return HybridDecision(
            composite_result=composite_result,
            raw_confidence=composite_result.confidence,
            status="candidate",
            reason=(
                f"Hybrid BUY score={composite_result.composite_score:.3f} "
                f"confidence={composite_result.confidence:.3f}"
            ),
            decision_source="hybrid_entry",
        )

    def _evaluate_exit(
        self,
        position: Any,
        market_price: Decimal,
        composite_result: CompositeScoreResult,
        config: dict[str, Any],
        regime: str | None = None,
    ) -> HybridDecision | None:
        """Evaluate exit conditions for an open position.

        Returns HybridDecision if an exit/hold action should be taken,
        or None if no exit-specific action is needed (allow entry logic to proceed).
        """
        prior_trailing_stop = getattr(position, "trailing_stop_price", None)
        exit_decision = evaluate_exit(
            position=position,
            current_price=market_price,
            composite_score=composite_result.composite_score,
            config=config,
            now=datetime.now(timezone.utc),
            regime=regime,
        )

        if exit_decision.action == "SELL":
            signal = TradeSignal(
                action=TradeSide.SELL,
                symbol=getattr(position, "symbol", "BTCUSDT"),
                quantity_pct=exit_decision.quantity_pct,
                reason=exit_decision.reason,
            )
            return HybridDecision(
                signal=signal,
                composite_result=composite_result,
                exit_decision=exit_decision,
                status="signal",
                reason=exit_decision.reason,
                decision_source="hybrid_exit",
            )

        # No sell, but trailing stop may have updated
        if (
            exit_decision.updated_trailing_stop_price is not None
            and exit_decision.updated_trailing_stop_price != prior_trailing_stop
        ):
            return HybridDecision(
                composite_result=composite_result,
                exit_decision=exit_decision,
                status="hold",
                reason="Trailing stop updated",
                decision_source="hybrid_exit",
            )

        return HybridDecision(
            composite_result=composite_result,
            exit_decision=exit_decision,
            status="hold",
            reason="Position open; no hybrid exit signal",
            decision_source="hybrid_exit",
        )

    def _compute_sizing(
        self,
        indicators: dict,
        context: StrategyContext,
        final_confidence: float,
    ) -> tuple[PositionSizingResult, str | None] | None:
        """Compute position sizing. Returns (sizing, skip_reason) or None if ATR unavailable."""
        config = context.config
        atr_values = indicators.get("atr", [])
        if not atr_values:
            return None

        take_profit_ratio = Decimal(str(config.get("take_profit_ratio", 2.0)))
        min_reward_risk_ratio = Decimal(str(config.get("min_reward_risk_ratio", 1.5)))
        if take_profit_ratio < min_reward_risk_ratio:
            return (
                PositionSizingResult(
                    quantity_pct=Decimal("0"),
                    stop_loss_price=context.market_price,
                    take_profit_price=context.market_price,
                    risk_amount=Decimal("0"),
                    position_value=Decimal("0"),
                    stop_distance=Decimal("0"),
                    stop_distance_pct=Decimal("0"),
                    confidence_multiplier=Decimal("1"),
                    streak_multiplier=Decimal("1"),
                    entry_atr=Decimal(str(atr_values[-1])),
                ),
                "Configured reward/risk ratio below minimum",
            )

        confidence_tier = (
            "full" if final_confidence >= 0.8
            else "reduced" if final_confidence >= 0.6
            else "small"
        )

        sizing = calculate_position_size(
            equity=context.equity,
            entry_price=context.market_price,
            atr=Decimal(str(atr_values[-1])),
            atr_multiplier=Decimal(str(config.get("atr_stop_multiplier", 2.0))),
            risk_per_trade_pct=context.risk_per_trade_pct,
            confidence_tier=confidence_tier,
            losing_streak_count=context.consecutive_losses,
            max_position_pct=context.max_position_size_pct,
            take_profit_ratio=take_profit_ratio,
        )

        if sizing.quantity_pct <= Decimal("0"):
            return sizing, "Hybrid sizing produced zero quantity"

        return sizing, None

    def compute_sizing(
        self,
        indicators: dict,
        context: StrategyContext,
        final_confidence: float,
    ) -> tuple[PositionSizingResult, str | None] | None:
        return self._compute_sizing(indicators, context, final_confidence)
