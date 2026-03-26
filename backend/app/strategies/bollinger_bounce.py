"""Bollinger Bounce strategy — buy at or near lower band, sell at upper band."""

from __future__ import annotations

from decimal import Decimal

from app.engine.executor import TradeSignal
from app.models.enums import TradeSide
from app.strategies.base import BaseStrategy


class BollingerBounceStrategy(BaseStrategy):
    """Buy when price touches/crosses below lower Bollinger Band,
    sell when it touches/crosses above upper band.

    Uses close price relative to bands for signal generation.
    """

    def decide(
        self,
        indicators: dict,
        has_position: bool,
        available_usdt: Decimal,
    ) -> TradeSignal | None:
        bb = indicators.get("bollinger_bands", ([], [], []))
        if len(bb) != 3:
            return None

        upper, middle, lower = bb
        if not upper or not lower or not middle:
            return None

        latest_close = indicators.get("latest_close")
        previous_close = indicators.get("previous_close")
        if latest_close is None or previous_close is None:
            return None

        curr_upper = upper[-1]
        curr_lower = lower[-1]
        curr_middle = middle[-1]

        symbol = str(indicators.get("symbol") or "BTCUSDT")

        # BUY: Price at or near lower band (oversold bounce)
        if not has_position:
            band_width = curr_upper - curr_lower
            if band_width > 0:
                # Proximity: how close price is to the lower band (0.0 = at band, 1.0 = at middle)
                proximity = (latest_close - curr_lower) / band_width

                if latest_close <= curr_lower:
                    # At or below the band — strongest signal
                    depth = (curr_lower - latest_close) / band_width
                    qty_pct = Decimal("0.5") if depth > 0.1 else Decimal("0.3")
                    return TradeSignal(
                        action=TradeSide.BUY,
                        symbol=symbol,
                        quantity_pct=qty_pct,
                        reason=(
                            f"Bollinger bounce BUY: close({latest_close:.2f}) <= "
                            f"lower({curr_lower:.2f}), middle={curr_middle:.2f}"
                        ),
                    )

                if proximity <= 0.20:
                    # Within 20% of lower band — weaker signal, smaller position
                    return TradeSignal(
                        action=TradeSide.BUY,
                        symbol=symbol,
                        quantity_pct=Decimal("0.2"),
                        reason=(
                            f"Bollinger proximity BUY: close({latest_close:.2f}) within "
                            f"{proximity:.0%} of lower({curr_lower:.2f}), middle={curr_middle:.2f}"
                        ),
                    )

        # SELL: Price touches or crosses above upper band (overbought)
        if latest_close >= curr_upper and has_position:
            return TradeSignal(
                action=TradeSide.SELL,
                symbol=symbol,
                quantity_pct=Decimal("1.0"),
                reason=(
                    f"Bollinger bounce SELL: close({latest_close:.2f}) >= "
                    f"upper({curr_upper:.2f}), middle={curr_middle:.2f}"
                ),
            )

        # Also sell if price drops back below middle band after buying (cut losses)
        if latest_close < curr_middle and previous_close >= curr_middle and has_position:
            return TradeSignal(
                action=TradeSide.SELL,
                symbol=symbol,
                quantity_pct=Decimal("1.0"),
                reason=(
                    f"Bollinger bounce SELL (middle cross): close({latest_close:.2f}) "
                    f"crossed below middle({curr_middle:.2f})"
                ),
            )

        return None  # HOLD
