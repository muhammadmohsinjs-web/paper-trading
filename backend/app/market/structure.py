"""Support and resistance detection using fractal swing highs/lows.

Identifies key price levels where price has historically reversed,
clusters nearby levels, and ranks by touch count (strength).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SRLevel:
    price: float
    strength: int  # Number of touches / swing points clustered here
    level_type: str  # "support" or "resistance"


def _find_fractal_highs(
    highs: list[float],
    order: int = 5,
) -> list[tuple[int, float]]:
    """Find fractal highs: highs[i] is the max of highs[i-order:i+order+1]."""
    results: list[tuple[int, float]] = []
    for i in range(order, len(highs) - order):
        window = highs[i - order : i + order + 1]
        if highs[i] == max(window):
            results.append((i, highs[i]))
    return results


def _find_fractal_lows(
    lows: list[float],
    order: int = 5,
) -> list[tuple[int, float]]:
    """Find fractal lows: lows[i] is the min of lows[i-order:i+order+1]."""
    results: list[tuple[int, float]] = []
    for i in range(order, len(lows) - order):
        window = lows[i - order : i + order + 1]
        if lows[i] == min(window):
            results.append((i, lows[i]))
    return results


def _cluster_levels(
    prices: list[float],
    cluster_pct: float = 0.5,
) -> list[tuple[float, int]]:
    """Cluster nearby prices and return (average_price, count) pairs.

    Two prices within cluster_pct% of each other are merged.
    """
    if not prices:
        return []

    sorted_prices = sorted(prices)
    clusters: list[list[float]] = [[sorted_prices[0]]]

    for price in sorted_prices[1:]:
        cluster_center = sum(clusters[-1]) / len(clusters[-1])
        if abs(price - cluster_center) / cluster_center * 100 <= cluster_pct:
            clusters[-1].append(price)
        else:
            clusters.append([price])

    return [
        (sum(cluster) / len(cluster), len(cluster))
        for cluster in clusters
    ]


def find_sr_levels(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    order: int = 5,
    cluster_pct: float = 0.5,
    min_strength: int = 2,
) -> list[SRLevel]:
    """Find support and resistance levels from fractal swing points.

    Args:
        highs: High prices.
        lows: Low prices.
        closes: Close prices (used to classify levels relative to current price).
        order: Fractal order — N bars on each side for swing detection.
        cluster_pct: Percentage range for clustering nearby levels.
        min_strength: Minimum touch count to include a level.

    Returns:
        List of SRLevel sorted by proximity to current price.
    """
    if len(highs) < 2 * order + 1 or len(lows) < 2 * order + 1:
        return []

    current_price = closes[-1] if closes else 0

    # Detect swing points
    swing_highs = _find_fractal_highs(highs, order)
    swing_lows = _find_fractal_lows(lows, order)

    # Cluster resistance levels (from swing highs)
    resistance_prices = [price for _, price in swing_highs]
    resistance_clusters = _cluster_levels(resistance_prices, cluster_pct)

    # Cluster support levels (from swing lows)
    support_prices = [price for _, price in swing_lows]
    support_clusters = _cluster_levels(support_prices, cluster_pct)

    levels: list[SRLevel] = []

    for price, count in resistance_clusters:
        if count >= min_strength:
            # Classify based on current price
            level_type = "resistance" if price > current_price else "support"
            levels.append(SRLevel(
                price=round(price, 8),
                strength=count,
                level_type=level_type,
            ))

    for price, count in support_clusters:
        if count >= min_strength:
            level_type = "support" if price < current_price else "resistance"
            # Avoid duplicates: skip if there's already a level very close
            is_duplicate = any(
                abs(existing.price - price) / price * 100 < cluster_pct
                for existing in levels
            )
            if not is_duplicate:
                levels.append(SRLevel(
                    price=round(price, 8),
                    strength=count,
                    level_type=level_type,
                ))

    # Sort by proximity to current price
    levels.sort(key=lambda level: abs(level.price - current_price))

    return levels


def nearest_support(levels: list[SRLevel], current_price: float) -> SRLevel | None:
    """Find the nearest support level below current price."""
    supports = [
        level for level in levels
        if level.level_type == "support" and level.price < current_price
    ]
    return max(supports, key=lambda s: s.price) if supports else None


def nearest_resistance(levels: list[SRLevel], current_price: float) -> SRLevel | None:
    """Find the nearest resistance level above current price."""
    resistances = [
        level for level in levels
        if level.level_type == "resistance" and level.price > current_price
    ]
    return min(resistances, key=lambda r: r.price) if resistances else None
