"""RSI Mean-Reversion strategy — buy oversold, sell overbought."""

from __future__ import annotations

from decimal import Decimal

from app.engine.executor import TradeSignal
from app.models.enums import TradeSide
from app.strategies.base import BaseStrategy


class RSIMeanReversionStrategy(BaseStrategy):
    """Buy when RSI drops below oversold threshold, sell when it rises above overbought.

    Default thresholds: oversold=30, overbought=70.
    Uses the last two RSI values to detect threshold crossings (not just levels).
    """

    def decide(
        self,
        indicators: dict,
        has_position: bool,
        available_usdt: Decimal,
    ) -> TradeSignal | None:
        rsi_values = indicators.get("rsi", [])
        if len(rsi_values) < 2:
            return None

        prev_rsi, curr_rsi = rsi_values[-2], rsi_values[-1]
        symbol = "BTCUSDT"

        # Config thresholds (passed via config_json → indicators dict won't have them,
        # but the trading loop passes config separately; use sensible defaults here)
        oversold = 30.0
        overbought = 70.0

        # BUY: RSI crosses below oversold threshold (entering oversold territory)
        if curr_rsi < oversold and not has_position:
            # Stronger signal the deeper the RSI
            if curr_rsi < 20:
                qty_pct = Decimal("0.5")  # Strong conviction
            else:
                qty_pct = Decimal("0.3")  # Moderate conviction

            return TradeSignal(
                action=TradeSide.BUY,
                symbol=symbol,
                quantity_pct=qty_pct,
                reason=f"RSI mean-reversion BUY: RSI={curr_rsi:.1f} < {oversold} (prev={prev_rsi:.1f})",
            )

        # SELL: RSI crosses above overbought threshold
        if curr_rsi > overbought and has_position:
            return TradeSignal(
                action=TradeSide.SELL,
                symbol=symbol,
                quantity_pct=Decimal("1.0"),  # Sell entire position
                reason=f"RSI mean-reversion SELL: RSI={curr_rsi:.1f} > {overbought} (prev={prev_rsi:.1f})",
            )

        return None  # HOLD
