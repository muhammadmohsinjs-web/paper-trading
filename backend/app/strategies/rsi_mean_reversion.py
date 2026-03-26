"""RSI Mean-Reversion strategy — divergence-first, deep oversold fallback.

Primary signal: bullish RSI divergence (price makes lower low, RSI makes
higher low). This indicates momentum exhaustion and is the highest-probability
mean-reversion signal in crypto.

Fallback: RSI drops below 20 (deep oversold) without divergence — still
a valid entry but lower conviction.

RSI 20-30 without divergence is intentionally skipped — it catches too many
falling knives in trending markets.
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
        if divergence is not None and divergence.detected and divergence.divergence_type == "bullish":
            return TradeSignal(
                action=TradeSide.BUY,
                symbol=symbol,
                quantity_pct=Decimal("0.5"),  # High conviction — divergence confirmed
                reason=(
                    f"RSI bullish divergence: price lower low "
                    f"({divergence.price_pivot_2:.2f} < {divergence.price_pivot_1:.2f}) "
                    f"but RSI higher low ({divergence.rsi_pivot_2:.1f} > {divergence.rsi_pivot_1:.1f}), "
                    f"current RSI={curr_rsi:.1f}, strength={divergence.strength:.2f}"
                ),
            )

        # Fallback: deep oversold only (RSI < 20)
        if curr_rsi < 20:
            return TradeSignal(
                action=TradeSide.BUY,
                symbol=symbol,
                quantity_pct=Decimal("0.3"),  # Lower conviction — no divergence
                reason=f"RSI deep oversold BUY: RSI={curr_rsi:.1f} < 20 (no divergence, prev={prev_rsi:.1f})",
            )

        # RSI 20-30 without divergence: intentionally skip (falling knife territory)
        return None
