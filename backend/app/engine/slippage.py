"""Slippage simulation for realistic paper trading.

Direction is always adverse: buys slip up, sells slip down.

| Order Size   | Slippage Range  |
|-------------|-----------------|
| Under $10k  | 0.01% - 0.05%  |
| $10k - $50k | 0.05% - 0.15%  |
| $50k+       | 0.10% - 0.30%  |
"""

from __future__ import annotations

import random
from decimal import Decimal

from app.models.enums import TradeSide

# (min_rate, max_rate) per notional tier
_TIERS: list[tuple[Decimal, Decimal, Decimal]] = [
    (Decimal("10000"), Decimal("0.0001"), Decimal("0.0005")),   # < 10k
    (Decimal("50000"), Decimal("0.0005"), Decimal("0.0015")),   # 10k–50k
    (Decimal("Infinity"), Decimal("0.001"), Decimal("0.003")),  # 50k+
]


def estimate_slippage_rate(notional: Decimal) -> Decimal:
    """Return the midpoint slippage rate for a notional tier."""
    for threshold, lo, hi in _TIERS:
        if notional < threshold:
            return ((lo + hi) / 2).quantize(Decimal("0.0000001"))
    return Decimal("0.001")


def estimate_liquidity_adjusted_slippage_rate(
    notional: Decimal,
    *,
    volume_24h_usdt: float | None = None,
    market_quality_score: float | None = None,
    spread_bps: float | None = None,
    depth_multiple: float | None = None,
) -> Decimal:
    """Estimate slippage with a simple liquidity-aware penalty.

    The base tiers still anchor the estimate by order size, but the rate is
    increased when the intended order consumes a material share of 24h volume
    or when the market-quality score is weak.
    """
    base_rate = estimate_slippage_rate(notional)
    multiplier = Decimal("1.0")
    spread_floor = Decimal("0")

    if volume_24h_usdt is not None and volume_24h_usdt > 0:
        participation = float(notional) / float(volume_24h_usdt)
        if participation >= 0.01:
            multiplier *= Decimal("1.75")
        elif participation >= 0.005:
            multiplier *= Decimal("1.45")
        elif participation >= 0.002:
            multiplier *= Decimal("1.25")
        elif participation >= 0.001:
            multiplier *= Decimal("1.10")

    if market_quality_score is not None:
        deficit = max(0.0, 0.60 - float(market_quality_score))
        multiplier *= Decimal(str(1.0 + min(deficit * 0.75, 0.30)))

    adjusted = (base_rate * multiplier).quantize(Decimal("0.0000001"))

    if spread_bps is not None and spread_bps > 0:
        half_spread_rate = (Decimal(str(spread_bps)) / Decimal("10000")) / Decimal("2")
        spread_floor = half_spread_rate.quantize(Decimal("0.0000001"))
        adjusted = max(adjusted, spread_floor)

    if depth_multiple is not None and depth_multiple > 0:
        if depth_multiple < 4:
            adjusted *= Decimal("1.30")
        elif depth_multiple < 7:
            adjusted *= Decimal("1.15")

    cap = (base_rate * Decimal("3.0")).quantize(Decimal("0.0000001"))
    return max(spread_floor, min(adjusted.quantize(Decimal("0.0000001")), cap))


def _pick_rate(notional: Decimal) -> Decimal:
    for threshold, lo, hi in _TIERS:
        if notional < threshold:
            if notional < Decimal("10000"):
                # Deterministic midpoint for small orders
                rate = estimate_slippage_rate(notional)
            else:
                rate = Decimal(str(random.uniform(float(lo), float(hi))))
            return rate.quantize(Decimal("0.0000001"))
    # fallback (should not reach here)
    return Decimal("0.001")


def apply_slippage(
    price: Decimal,
    notional: Decimal,
    side: TradeSide,
) -> tuple[Decimal, Decimal]:
    """Apply adverse slippage to a price.

    Args:
        price: Market price before slippage.
        notional: Order notional value (price * quantity).
        side: BUY or SELL.

    Returns:
        (execution_price, slippage_amount) — slippage is always positive.
    """
    rate = _pick_rate(notional)
    slippage_amount = (price * rate).quantize(Decimal("0.00000001"))

    if side == TradeSide.BUY:
        exec_price = price + slippage_amount
    else:
        exec_price = price - slippage_amount

    return exec_price, slippage_amount
