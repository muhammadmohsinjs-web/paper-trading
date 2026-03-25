"""Rule-based market regime classifier.

Uses ADX, Bollinger Band width, SMA slope, volume, and price action
to classify the current market into one of five regimes.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app.regime.types import MarketRegime, RegimeResult

logger = logging.getLogger(__name__)

# Thresholds (tunable)
ADX_TREND_THRESHOLD = 25.0
ADX_STRONG_TREND_THRESHOLD = 40.0
ADX_WEAK_THRESHOLD = 20.0
BB_WIDTH_HIGH_VOL_MULTIPLIER = 2.0
CRASH_PRICE_DROP_PCT = 5.0
CRASH_VOLUME_SPIKE_MULTIPLIER = 3.0
SMA_SLOPE_PERIODS = 10


class RegimeClassifier:
    """Stateless rule-based market regime detector."""

    def classify(self, indicators: dict[str, Any]) -> RegimeResult:
        """Classify market regime from computed indicators.

        Required indicator keys: closes (or latest_close/previous_close),
        and ideally: adx, bollinger_bands, sma_short, sma_long, atr, volume_ratio
        """
        metrics: dict[str, Any] = {}

        # Extract values
        adx_values = indicators.get("adx", [])
        latest_adx = adx_values[-1] if adx_values else None
        metrics["adx"] = round(latest_adx, 2) if latest_adx is not None else None

        # Bollinger Band width
        bb = indicators.get("bollinger_bands", ([], [], []))
        bb_upper, bb_middle, bb_lower = bb if len(bb) == 3 else ([], [], [])
        bb_width = None
        bb_width_avg = None
        if bb_upper and bb_middle and bb_lower and bb_middle[-1] != 0:
            bb_width = (bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]
            if len(bb_upper) >= 20:
                widths = [
                    (bb_upper[i] - bb_lower[i]) / bb_middle[i]
                    for i in range(max(0, len(bb_upper) - 20), len(bb_upper))
                    if bb_middle[i] != 0
                ]
                bb_width_avg = float(np.mean(widths)) if widths else None
        metrics["bb_width"] = round(bb_width, 4) if bb_width is not None else None
        metrics["bb_width_avg"] = round(bb_width_avg, 4) if bb_width_avg is not None else None

        # SMA slope (trend direction)
        sma_short = indicators.get("sma_short", [])
        sma_slope = None
        if len(sma_short) >= SMA_SLOPE_PERIODS:
            recent = sma_short[-SMA_SLOPE_PERIODS:]
            sma_slope = (recent[-1] - recent[0]) / recent[0] * 100 if recent[0] != 0 else 0
        metrics["sma_slope_pct"] = round(sma_slope, 4) if sma_slope is not None else None

        # Volume ratio
        volume_ratio_values = indicators.get("volume_ratio", [])
        latest_volume_ratio = volume_ratio_values[-1] if volume_ratio_values else None
        metrics["volume_ratio"] = round(latest_volume_ratio, 2) if latest_volume_ratio is not None else None

        # Price change
        latest_close = indicators.get("latest_close")
        previous_close = indicators.get("previous_close")
        price_change_pct = None
        if latest_close and previous_close and previous_close != 0:
            price_change_pct = (latest_close - previous_close) / previous_close * 100
        metrics["price_change_pct"] = round(price_change_pct, 4) if price_change_pct is not None else None

        # ── Classification logic ──────────────────────────────────────

        # 1. CRASH detection: large price drop + volume spike
        if self._is_crash(price_change_pct, latest_volume_ratio, sma_slope):
            return RegimeResult(
                regime=MarketRegime.CRASH,
                confidence=0.9,
                metrics=metrics,
                reasoning="Large price drop with volume spike detected",
            )

        # 2. HIGH_VOLATILITY: BB width > 2x average
        if self._is_high_volatility(bb_width, bb_width_avg, latest_adx):
            confidence = 0.7
            if latest_adx is not None and latest_adx < ADX_WEAK_THRESHOLD:
                confidence = 0.85  # volatile but not trending = choppy
            return RegimeResult(
                regime=MarketRegime.HIGH_VOLATILITY,
                confidence=confidence,
                metrics=metrics,
                reasoning="Bollinger Band width significantly above average",
            )

        # 3. TRENDING (UP or DOWN): ADX > 25 + SMA slope direction
        if latest_adx is not None and latest_adx >= ADX_TREND_THRESHOLD:
            if sma_slope is not None and sma_slope > 0:
                confidence = min(0.5 + (latest_adx - ADX_TREND_THRESHOLD) / 30, 0.95)
                return RegimeResult(
                    regime=MarketRegime.TRENDING_UP,
                    confidence=confidence,
                    metrics=metrics,
                    reasoning=f"ADX={latest_adx:.1f} with positive SMA slope={sma_slope:.2f}%",
                )
            elif sma_slope is not None and sma_slope < 0:
                confidence = min(0.5 + (latest_adx - ADX_TREND_THRESHOLD) / 30, 0.95)
                return RegimeResult(
                    regime=MarketRegime.TRENDING_DOWN,
                    confidence=confidence,
                    metrics=metrics,
                    reasoning=f"ADX={latest_adx:.1f} with negative SMA slope={sma_slope:.2f}%",
                )
            else:
                # ADX high but no slope — default to ranging
                return RegimeResult(
                    regime=MarketRegime.RANGING,
                    confidence=0.5,
                    metrics=metrics,
                    reasoning=f"ADX={latest_adx:.1f} but flat SMA slope",
                )

        # 4. RANGING: ADX < 25 (low trend strength)
        confidence = 0.6
        if latest_adx is not None and latest_adx < ADX_WEAK_THRESHOLD:
            confidence = 0.8
        return RegimeResult(
            regime=MarketRegime.RANGING,
            confidence=confidence,
            metrics=metrics,
            reasoning=f"ADX={latest_adx or 'N/A'} below trend threshold, market is ranging",
        )

    def _is_crash(
        self,
        price_change_pct: float | None,
        volume_ratio: float | None,
        sma_slope: float | None,
    ) -> bool:
        """Detect crash: price drop > 5% with volume spike > 3x."""
        if price_change_pct is None:
            return False

        has_price_drop = price_change_pct <= -CRASH_PRICE_DROP_PCT
        has_volume_spike = (
            volume_ratio is not None
            and volume_ratio >= CRASH_VOLUME_SPIKE_MULTIPLIER
        )
        has_steep_slope = sma_slope is not None and sma_slope <= -3.0

        # Need price drop + at least one confirming signal
        return has_price_drop and (has_volume_spike or has_steep_slope)

    def _is_high_volatility(
        self,
        bb_width: float | None,
        bb_width_avg: float | None,
        adx_value: float | None,
    ) -> bool:
        """Detect high volatility: BB width > 2x its average."""
        if bb_width is None or bb_width_avg is None or bb_width_avg == 0:
            return False
        return bb_width > bb_width_avg * BB_WIDTH_HIGH_VOL_MULTIPLIER
