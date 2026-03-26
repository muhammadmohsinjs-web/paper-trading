"""Multi-timeframe confluence filter.

Checks whether the higher timeframe (4h) trend aligns with a proposed
entry on the primary timeframe (1h/5m). Applies a confidence penalty
when the 4h trend is bearish, and provides a confidence boost when
fully aligned. Strong downtrends (RSI < 35) still hard-block entries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.market.data_store import DataStore
from app.market.indicators import ema, rsi, sma

logger = logging.getLogger(__name__)

# Higher timeframe interval to check against
HTF_INTERVAL = "4h"
MIN_HTF_CANDLES = 60  # Need at least 60 4h candles (~10 days)


@dataclass(frozen=True)
class MTFResult:
    htf_trend: str  # "up", "down", "neutral"
    aligned: bool  # Does HTF agree with proposed entry?
    confidence_boost: float  # 0.0 to 0.15 bonus if aligned
    reason: str


def check_confluence(
    symbol: str,
    proposed_action: str,
    primary_interval: str = "1h",
) -> MTFResult:
    """Check if higher timeframe supports the proposed trade direction.

    For BUY entries:
    - HTF trend "up" → aligned=True, confidence_boost=+0.10
    - HTF trend "neutral" → aligned=True, confidence_boost=0.0
    - HTF trend "down" (mild) → aligned=True, confidence_boost=-0.15
    - HTF trend "down" (strong, RSI<35) → aligned=False (hard block)

    For SELL entries: always aligned (we always want to exit).
    """
    if proposed_action != "BUY":
        return MTFResult(
            htf_trend="neutral",
            aligned=True,
            confidence_boost=0.0,
            reason="Exits always allowed regardless of HTF",
        )

    store = DataStore.get_instance()
    candles = store.get_candles(symbol, HTF_INTERVAL, 200)

    if len(candles) < MIN_HTF_CANDLES:
        # Not enough HTF data — allow entry but no boost
        logger.debug(
            "MTF confluence: only %d/%d 4h candles for %s, skipping filter",
            len(candles), MIN_HTF_CANDLES, symbol,
        )
        return MTFResult(
            htf_trend="neutral",
            aligned=True,
            confidence_boost=0.0,
            reason=f"Insufficient 4h data ({len(candles)}/{MIN_HTF_CANDLES} candles)",
        )

    closes = [c.close for c in candles]

    # Compute HTF indicators
    sma_20 = sma(closes, 20)
    sma_50 = sma(closes, 50)
    rsi_14 = rsi(closes, 14)

    if not sma_20 or not sma_50 or not rsi_14:
        return MTFResult(
            htf_trend="neutral",
            aligned=True,
            confidence_boost=0.0,
            reason="Could not compute 4h indicators",
        )

    latest_sma_20 = sma_20[-1]
    latest_sma_50 = sma_50[-1]
    latest_rsi = rsi_14[-1]
    latest_close = closes[-1]

    # Determine HTF trend
    sma_bullish = latest_sma_20 > latest_sma_50
    sma_bearish = latest_sma_20 < latest_sma_50
    price_above_sma = latest_close > latest_sma_20
    rsi_bullish = latest_rsi > 50
    rsi_bearish = latest_rsi < 45

    if sma_bullish and rsi_bullish and price_above_sma:
        htf_trend = "up"
    elif sma_bearish and rsi_bearish and not price_above_sma:
        htf_trend = "down"
    else:
        htf_trend = "neutral"

    # Alignment check
    if htf_trend == "down":
        # Strong downtrend (RSI < 35): hard block — high probability of further decline
        if latest_rsi < 35:
            return MTFResult(
                htf_trend=htf_trend,
                aligned=False,
                confidence_boost=0.0,
                reason=(
                    f"4h strong downtrend (SMA20={latest_sma_20:.2f} < SMA50={latest_sma_50:.2f}, "
                    f"RSI={latest_rsi:.1f} < 35) — BUY blocked"
                ),
            )
        # Mild downtrend: allow with confidence penalty
        return MTFResult(
            htf_trend=htf_trend,
            aligned=True,
            confidence_boost=-0.15,
            reason=(
                f"4h mild bearish (SMA20={latest_sma_20:.2f} < SMA50={latest_sma_50:.2f}, "
                f"RSI={latest_rsi:.1f}) — confidence reduced"
            ),
        )

    confidence_boost = 0.10 if htf_trend == "up" else 0.0
    return MTFResult(
        htf_trend=htf_trend,
        aligned=True,
        confidence_boost=confidence_boost,
        reason=(
            f"4h trend={htf_trend} (SMA20={latest_sma_20:.2f}, "
            f"SMA50={latest_sma_50:.2f}, RSI={latest_rsi:.1f})"
        ),
    )
