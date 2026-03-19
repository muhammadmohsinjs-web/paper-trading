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


def _pick_rate(notional: Decimal) -> Decimal:
    for threshold, lo, hi in _TIERS:
        if notional < threshold:
            rate = (lo + hi) / 2
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
