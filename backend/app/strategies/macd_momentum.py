"""MACD Momentum strategy — buy/sell on MACD/signal line crossovers."""

from __future__ import annotations

from decimal import Decimal

from app.engine.executor import TradeSignal
from app.models.enums import TradeSide
from app.strategies.base import BaseStrategy


class MACDMomentumStrategy(BaseStrategy):
    """Buy when MACD line crosses above signal line, sell when it crosses below.

    Optionally confirms with histogram direction for stronger signals.
    """

    def decide(
        self,
        indicators: dict,
        has_position: bool,
        available_usdt: Decimal,
    ) -> TradeSignal | None:
        macd_data = indicators.get("macd", ([], [], []))
        if len(macd_data) != 3:
            return None

        macd_line, signal_line, histogram = macd_data
        if len(macd_line) < 2 or len(signal_line) < 2 or len(histogram) < 2:
            return None

        prev_macd, curr_macd = macd_line[-2], macd_line[-1]
        prev_signal, curr_signal = signal_line[-2], signal_line[-1]
        curr_hist = histogram[-1]
        prev_hist = histogram[-2]

        symbol = str(indicators.get("symbol") or "BTCUSDT")

        # Bullish crossover: MACD crosses above signal line
        if (
            prev_macd <= prev_signal
            and curr_macd > curr_signal
            and not has_position
        ):
            # Stronger signal if histogram is accelerating
            if curr_hist > prev_hist and curr_hist > 0:
                qty_pct = Decimal("0.5")  # Strong momentum
            else:
                qty_pct = Decimal("0.3")  # Standard crossover

            return TradeSignal(
                action=TradeSide.BUY,
                symbol=symbol,
                quantity_pct=qty_pct,
                reason=(
                    f"MACD momentum BUY: MACD({curr_macd:.2f}) crossed above "
                    f"signal({curr_signal:.2f}), hist={curr_hist:.2f}"
                ),
            )

        # Bearish crossover: MACD crosses below signal line
        if (
            prev_macd >= prev_signal
            and curr_macd < curr_signal
            and has_position
        ):
            return TradeSignal(
                action=TradeSide.SELL,
                symbol=symbol,
                quantity_pct=Decimal("1.0"),  # Sell entire position
                reason=(
                    f"MACD momentum SELL: MACD({curr_macd:.2f}) crossed below "
                    f"signal({curr_signal:.2f}), hist={curr_hist:.2f}"
                ),
            )

        return None  # HOLD
