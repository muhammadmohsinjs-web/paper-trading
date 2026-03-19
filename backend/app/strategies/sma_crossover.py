"""Simple SMA crossover strategy — Phase 1 placeholder."""

from __future__ import annotations

from decimal import Decimal

from app.engine.executor import TradeSignal
from app.models.enums import TradeSide
from app.strategies.base import BaseStrategy


class SMACrossoverStrategy(BaseStrategy):
    """Buy when short SMA crosses above long SMA, sell when it crosses below.

    Uses the last two values of each SMA to detect crossovers.
    """

    def decide(
        self,
        indicators: dict,
        has_position: bool,
        available_usdt: Decimal,
    ) -> TradeSignal | None:
        sma_short = indicators.get("sma_short", [])
        sma_long = indicators.get("sma_long", [])

        if len(sma_short) < 2 or len(sma_long) < 2:
            return None  # Not enough data

        # Align: use last 2 from each
        prev_short, curr_short = sma_short[-2], sma_short[-1]
        prev_long, curr_long = sma_long[-2], sma_long[-1]

        symbol = "BTCUSDT"

        # Golden cross: short crosses above long → BUY (with volume confirmation)
        if prev_short <= prev_long and curr_short > curr_long and not has_position:
            volume_ratio = indicators.get("volume_ratio")
            if volume_ratio is not None and volume_ratio < 1.2:
                return None  # Reject crossover without above-average volume
            return TradeSignal(
                action=TradeSide.BUY,
                symbol=symbol,
                quantity_pct=Decimal("0.5"),  # Risk layer will further cap
                reason=f"SMA crossover BUY: short({curr_short:.2f}) > long({curr_long:.2f}) vol_ratio={volume_ratio or 'n/a'}",
            )

        # Death cross: short crosses below long → SELL
        if prev_short >= prev_long and curr_short < curr_long and has_position:
            return TradeSignal(
                action=TradeSide.SELL,
                symbol=symbol,
                quantity_pct=Decimal("1.0"),  # Sell all
                reason=f"SMA crossover SELL: short({curr_short:.2f}) < long({curr_long:.2f})",
            )

        return None  # HOLD
