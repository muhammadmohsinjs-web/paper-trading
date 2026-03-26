"""RSI divergence detection.

Detects bullish divergence (price makes lower low, RSI makes higher low)
and bearish divergence (price makes higher high, RSI makes lower high).

These are among the most reliable mean-reversion signals in crypto markets
because they indicate momentum exhaustion before a reversal.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DivergenceResult:
    detected: bool
    divergence_type: str  # "bullish", "bearish", "none"
    strength: float  # 0.0 to 1.0
    price_pivot_1: float | None = None  # Earlier pivot
    price_pivot_2: float | None = None  # Later pivot
    rsi_pivot_1: float | None = None
    rsi_pivot_2: float | None = None


NO_DIVERGENCE = DivergenceResult(
    detected=False, divergence_type="none", strength=0.0
)


def _find_swing_lows(
    values: list[float],
    order: int = 3,
    lookback: int = 30,
) -> list[tuple[int, float]]:
    """Find local minima within the lookback window.

    A swing low at index i means values[i] is the minimum of
    values[i-order : i+order+1].
    """
    if len(values) < lookback:
        return []

    start = max(order, len(values) - lookback)
    end = len(values) - order
    swings: list[tuple[int, float]] = []

    for i in range(start, end):
        window = values[i - order : i + order + 1]
        if values[i] == min(window):
            swings.append((i, values[i]))

    return swings


def _find_swing_highs(
    values: list[float],
    order: int = 3,
    lookback: int = 30,
) -> list[tuple[int, float]]:
    """Find local maxima within the lookback window."""
    if len(values) < lookback:
        return []

    start = max(order, len(values) - lookback)
    end = len(values) - order
    swings: list[tuple[int, float]] = []

    for i in range(start, end):
        window = values[i - order : i + order + 1]
        if values[i] == max(window):
            swings.append((i, values[i]))

    return swings


def detect_rsi_divergence(
    closes: list[float],
    rsi_values: list[float],
    lookback: int = 30,
    min_distance: int = 5,
) -> DivergenceResult:
    """Detect bullish or bearish RSI divergence.

    Bullish divergence: price makes a lower low, RSI makes a higher low.
    Bearish divergence: price makes a higher high, RSI makes a lower high.

    Args:
        closes: Price close values (full series).
        rsi_values: RSI values (may be shorter than closes due to RSI warmup).
        lookback: Number of bars to look back for swing detection.
        min_distance: Minimum bars between two pivots to avoid noise.

    Returns:
        DivergenceResult with detection status and strength.
    """
    if len(closes) < lookback or len(rsi_values) < lookback:
        return NO_DIVERGENCE

    # Align RSI to the end of closes (RSI is shorter due to warmup period)
    rsi_offset = len(closes) - len(rsi_values)

    # Check for bullish divergence (swing lows)
    price_lows = _find_swing_lows(closes, order=3, lookback=lookback)
    if len(price_lows) >= 2:
        # Take the two most recent swing lows
        for i in range(len(price_lows) - 1):
            p1_idx, p1_price = price_lows[i]
            p2_idx, p2_price = price_lows[i + 1]

            if p2_idx - p1_idx < min_distance:
                continue

            # Price makes lower low
            if p2_price >= p1_price:
                continue

            # Get RSI at those indices
            rsi_idx_1 = p1_idx - rsi_offset
            rsi_idx_2 = p2_idx - rsi_offset
            if rsi_idx_1 < 0 or rsi_idx_2 < 0 or rsi_idx_1 >= len(rsi_values) or rsi_idx_2 >= len(rsi_values):
                continue

            rsi_1 = rsi_values[rsi_idx_1]
            rsi_2 = rsi_values[rsi_idx_2]

            # RSI makes higher low (divergence)
            if rsi_2 > rsi_1:
                # Strength: how much RSI diverged relative to its range
                rsi_diff = rsi_2 - rsi_1
                price_diff_pct = abs(p2_price - p1_price) / p1_price if p1_price else 0
                strength = min(1.0, (rsi_diff / 20.0) + (price_diff_pct * 5.0))

                return DivergenceResult(
                    detected=True,
                    divergence_type="bullish",
                    strength=max(0.3, min(strength, 1.0)),
                    price_pivot_1=p1_price,
                    price_pivot_2=p2_price,
                    rsi_pivot_1=rsi_1,
                    rsi_pivot_2=rsi_2,
                )

    # Check for bearish divergence (swing highs)
    price_highs = _find_swing_highs(closes, order=3, lookback=lookback)
    if len(price_highs) >= 2:
        for i in range(len(price_highs) - 1):
            p1_idx, p1_price = price_highs[i]
            p2_idx, p2_price = price_highs[i + 1]

            if p2_idx - p1_idx < min_distance:
                continue

            # Price makes higher high
            if p2_price <= p1_price:
                continue

            rsi_idx_1 = p1_idx - rsi_offset
            rsi_idx_2 = p2_idx - rsi_offset
            if rsi_idx_1 < 0 or rsi_idx_2 < 0 or rsi_idx_1 >= len(rsi_values) or rsi_idx_2 >= len(rsi_values):
                continue

            rsi_1 = rsi_values[rsi_idx_1]
            rsi_2 = rsi_values[rsi_idx_2]

            # RSI makes lower high (divergence)
            if rsi_2 < rsi_1:
                rsi_diff = rsi_1 - rsi_2
                price_diff_pct = abs(p2_price - p1_price) / p1_price if p1_price else 0
                strength = min(1.0, (rsi_diff / 20.0) + (price_diff_pct * 5.0))

                return DivergenceResult(
                    detected=True,
                    divergence_type="bearish",
                    strength=max(0.3, min(strength, 1.0)),
                    price_pivot_1=p1_price,
                    price_pivot_2=p2_price,
                    rsi_pivot_1=rsi_1,
                    rsi_pivot_2=rsi_2,
                )

    return NO_DIVERGENCE
