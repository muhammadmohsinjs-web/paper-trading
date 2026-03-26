"""RSI Mean-Reversion strategy — divergence-first, oversold fallback.

Primary signal: bullish RSI divergence (price makes lower low, RSI makes
higher low). This indicates momentum exhaustion and is the highest-probability
mean-reversion signal in crypto.

Tiered oversold entries without divergence:
  - RSI < 20 (deep oversold) → medium conviction (0.3)
  - RSI < 25 (oversold) → small conviction (0.2)
  - RSI 25-35 with divergence → reduced conviction (0.3)
  - RSI 25-35 without divergence → skip (falling knife territory)
"""

from __future__ import annotations

from decimal import Decimal

from app.engine.executor import TradeSignal
from app.models.enums import TradeSide
from app.strategies.base import BaseStrategy


class RSIMeanReversionStrategy(BaseStrategy):
    """Buy on RSI divergence or deep oversold, sell on overbought."""

    def decide(
        self,
        indicators: dict,
        has_position: bool,
        available_usdt: Decimal,
    ) -> TradeSignal | None:
        rsi_values = indicators.get("rsi", [])
        if len(rsi_values) < 2:
            return None

        curr_rsi = rsi_values[-1]
        prev_rsi = rsi_values[-2]
        symbol = str(indicators.get("symbol") or "BTCUSDT")
        overbought = 70.0

        # SELL: RSI crosses above overbought threshold
        if curr_rsi > overbought and has_position:
            return TradeSignal(
                action=TradeSide.SELL,
                symbol=symbol,
                quantity_pct=Decimal("1.0"),
                reason=f"RSI mean-reversion SELL: RSI={curr_rsi:.1f} > {overbought} (prev={prev_rsi:.1f})",
            )

        if has_position:
            return None

        # BUY: Check for RSI divergence first (highest quality signal)
        divergence = indicators.get("rsi_divergence")
        has_divergence = (
            divergence is not None
            and divergence.detected
            and divergence.divergence_type == "bullish"
        )

        if has_divergence and curr_rsi < 35:
            qty = Decimal("0.5") if curr_rsi < 25 else Decimal("0.3")
            return TradeSignal(
                action=TradeSide.BUY,
                symbol=symbol,
                quantity_pct=qty,
                reason=(
                    f"RSI bullish divergence: price lower low "
                    f"({divergence.price_pivot_2:.2f} < {divergence.price_pivot_1:.2f}) "
                    f"but RSI higher low ({divergence.rsi_pivot_2:.1f} > {divergence.rsi_pivot_1:.1f}), "
                    f"current RSI={curr_rsi:.1f}, strength={divergence.strength:.2f}"
                ),
            )

        # Tiered oversold entries without divergence
        if curr_rsi < 20:
            return TradeSignal(
                action=TradeSide.BUY,
                symbol=symbol,
                quantity_pct=Decimal("0.3"),
                reason=f"RSI deep oversold BUY: RSI={curr_rsi:.1f} < 20 (no divergence, prev={prev_rsi:.1f})",
            )

        if curr_rsi < 25:
            return TradeSignal(
                action=TradeSide.BUY,
                symbol=symbol,
                quantity_pct=Decimal("0.2"),  # Small position — oversold but no divergence
                reason=f"RSI oversold BUY: RSI={curr_rsi:.1f} < 25 (no divergence, prev={prev_rsi:.1f})",
            )

        # RSI 25-35 without divergence: skip (falling knife territory)
        return None
